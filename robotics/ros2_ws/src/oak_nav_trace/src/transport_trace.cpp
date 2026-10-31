#include "../../../../timing/trace.hpp"
#include <dlfcn.h>
#include <rcl/publisher.h>
#include <rcl/subscription.h>
#include <gz/transport/Node.hh>
#include <gz/msgs/twist.pb.h>
#include <geometry_msgs/msg/twist_stamped.hpp>
#include <execinfo.h>
#include <pthread.h>
#include <semaphore.h>
#include <rmw_fastrtps_shared_cpp/custom_publisher_info.hpp>
#include <unordered_set>
#include <atomic>

namespace {
thread_local bool publishing = false;
thread_local bool unwinding_wait = false;
std::atomic<pthread_mutex_t *> send_mutex{nullptr};
std::atomic<long> send_owner{0};
thread_local unsigned long long send_held_since = 0;
thread_local bool resolving_site = false;
void waiting_stack(unsigned long long elapsed, const char *stage = "publish_wait_stack", bool unknown = false) {
  const char *enabled = std::getenv("OAK_TIMING_STACKS");
  if ((!unknown && elapsed < 50000000ULL) || !enabled || !*enabled || unwinding_wait) return;
  unwinding_wait = true;
  void *addresses[32];
  int count = backtrace(addresses, 32);
  for (int i=0; i<count; ++i) {
    Dl_info info{};
    if (!dladdr(addresses[i], &info) || !info.dli_fname) continue;
    auto fields = ",\"wait_ns\":"+std::to_string(elapsed)+",\"duration_known\":"+(unknown ? "false" : "true")+",\"frame\":"+std::to_string(i)+
      ",\"module\":\""+info.dli_fname+"\",\"offset\":"+
      std::to_string(reinterpret_cast<uintptr_t>(addresses[i])-reinterpret_cast<uintptr_t>(info.dli_fbase))+
      ",\"symbol\":\""+(info.dli_sname ? std::string(info.dli_sname) : "unknown")+"\"";
    oak_timing::record(stage, fields.c_str());
  }
  unwinding_wait = false;
}
bool relevant(const char *topic) {
  return topic && (std::strstr(topic, "cmd_vel") || std::strstr(topic, "actuator_cmd"));
}
void ros_record(const char *stage, const char *topic, const void *msg = nullptr,
                const rmw_message_info_t *info = nullptr) {
  char detail[512];
  // Only the fixed-layout six-double Twist is decoded, never C/C++ strings.
  if (msg && !std::strstr(topic, "leased")) {
    auto value = static_cast<const double *>(msg);
    std::snprintf(detail, sizeof(detail), ",\"topic\":\"%s\",\"vx\":%.9g,\"wz\":%.9g", topic, value[0], value[5]);
  } else std::snprintf(detail, sizeof(detail), ",\"topic\":\"%s\"", topic);
  std::string fields(detail);
  // The sole leased-topic subscriber inside the preloaded launch is the
  // installed C++ ros_gz_bridge. Python observers are launched without preload.
  if (msg && std::strcmp(stage, "dds_take") == 0 && std::strcmp(topic, "/oak/leased_cmd_vel") == 0) {
    auto stamped = static_cast<const geometry_msgs::msg::TwistStamped *>(msg);
    const auto &frame = stamped->header.frame_id;
    if (frame.find_first_not_of("oak-boottimev1/0123456789abcdef-") == std::string::npos)
      fields += ",\"frame_id\":\""+frame+"\"";
  }
  if (info) {
    fields += ",\"dds_source_realtime_ns\":"+std::to_string(info->source_timestamp)+
      ",\"dds_received_realtime_ns\":"+std::to_string(info->received_timestamp)+
      ",\"publication_sequence\":"+std::to_string(info->publication_sequence_number)+
      ",\"reception_sequence\":"+std::to_string(info->reception_sequence_number);
  }
  oak_timing::record(stage, fields.c_str());
}
}
extern "C" rcl_ret_t rcl_publish(const rcl_publisher_t *publisher, const void *msg,
                                  rmw_publisher_allocation_t *allocation) {
  using Function = rcl_ret_t (*)(const rcl_publisher_t *, const void *, rmw_publisher_allocation_t *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "rcl_publish"));
  const char *topic = rcl_publisher_get_topic_name(publisher);
  if (relevant(topic)) {
    static std::mutex qos_mutex;
    static std::unordered_set<const rcl_publisher_t *> observed;
    std::lock_guard<std::mutex> lock(qos_mutex);
    if (observed.insert(publisher).second) {
      auto rmw = rcl_publisher_get_rmw_handle(publisher);
      if (rmw) {
        auto qos = rcl_publisher_get_actual_qos(publisher);
        if (qos) {
          auto fields = ",\"topic\":\""+std::string(topic)+"\",\"implementation\":\""+rmw->implementation_identifier+
            "\",\"reliability\":"+std::to_string(qos->reliability)+",\"depth\":"+std::to_string(qos->depth);
          oak_timing::record("actual_ros_writer_qos", fields.c_str());
        }
      }
      if (rmw && std::strcmp(rmw->implementation_identifier, "rmw_fastrtps_cpp") == 0) {
        auto info = static_cast<CustomPublisherInfo *>(rmw->data);
        auto qos = info->data_writer_->get_qos();
        auto fields = ",\"topic\":\""+std::string(topic)+"\",\"publication_mode\":"+
          std::to_string(qos.publish_mode().kind)+",\"data_sharing\":"+
          std::to_string(qos.data_sharing().kind())+",\"max_blocking_ns\":"+
          std::to_string(static_cast<long long>(qos.reliability().max_blocking_time.seconds)*1000000000LL+qos.reliability().max_blocking_time.nanosec);
        oak_timing::record("actual_writer_qos", fields.c_str());
      }
    }
  }
  if (relevant(topic)) ros_record("dds_publish_begin", topic, msg);
  bool was_publishing = publishing;
  publishing = relevant(topic);
  auto result = original(publisher, msg, allocation);
  publishing = was_publishing;
  if (relevant(topic)) ros_record("dds_publish_end", topic);
  return result;
}
extern "C" int pthread_cond_timedwait(pthread_cond_t *condition, pthread_mutex_t *mutex,
                                       const timespec *timeout) {
  using Function = int (*)(pthread_cond_t *, pthread_mutex_t *, const timespec *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "pthread_cond_timedwait"));
  auto before = publishing ? oak_timing::clock_ns() : 0;
  int result = original(condition, mutex, timeout);
  if (publishing) waiting_stack(oak_timing::clock_ns()-before);
  return result;
}
extern "C" int pthread_cond_wait(pthread_cond_t *condition, pthread_mutex_t *mutex) {
  using Function = int (*)(pthread_cond_t *, pthread_mutex_t *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "pthread_cond_wait"));
  auto before = publishing && !unwinding_wait ? oak_timing::clock_ns() : 0;
  int result = original(condition, mutex);
  if (before) waiting_stack(oak_timing::clock_ns()-before);
  return result;
}
extern "C" int pthread_mutex_lock(pthread_mutex_t *mutex) {
  using Function = int (*)(pthread_mutex_t *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "pthread_mutex_lock"));
  if (!send_mutex.load() && publishing && !resolving_site && !unwinding_wait) {
    resolving_site = true;
    Dl_info info{};
    if (dladdr(__builtin_return_address(0), &info) && info.dli_sname &&
        std::strstr(info.dli_sname, "RTPSWriter8send_nts")) {
      send_mutex.store(mutex);
      oak_timing::record("send_resource_mutex_identified");
    }
    resolving_site = false;
  }
  bool watched = send_mutex.load() == mutex;
  auto before = (watched || publishing) && !unwinding_wait ? oak_timing::clock_ns() : 0;
  if (watched) {
    auto fields = ",\"recorded_owner_tid\":"+std::to_string(send_owner.load());
    oak_timing::record("send_resource_wait_begin", fields.c_str());
  }
  int result = original(mutex);
  if (watched && result == 0) {
    send_held_since = oak_timing::clock_ns();
    send_owner.store(syscall(SYS_gettid));
    auto fields = ",\"wait_ns\":"+std::to_string(send_held_since-before);
    oak_timing::record("send_resource_acquired", fields.c_str());
  }
  if (before) waiting_stack(oak_timing::clock_ns()-before);
  return result;
}
extern "C" int pthread_mutex_unlock(pthread_mutex_t *mutex) {
  using Function = int (*)(pthread_mutex_t *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "pthread_mutex_unlock"));
  if (send_mutex.load() == mutex) {
    auto held = send_held_since ? oak_timing::clock_ns()-send_held_since : 0;
    auto fields = ",\"held_ns\":"+std::to_string(held)+",\"duration_known\":"+(send_held_since ? "true" : "false");
    oak_timing::record("send_resource_releasing", fields.c_str());
    waiting_stack(held, "send_resource_owner_stack", send_held_since == 0);
    send_held_since = 0;
    send_owner.store(0);
  }
  return original(mutex);
}
extern "C" int pthread_cond_clockwait(pthread_cond_t *condition, pthread_mutex_t *mutex,
                                       clockid_t clock, const timespec *timeout) {
  using Function = int (*)(pthread_cond_t *, pthread_mutex_t *, clockid_t, const timespec *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "pthread_cond_clockwait"));
  auto before = publishing ? oak_timing::clock_ns() : 0;
  int result = original(condition, mutex, clock, timeout);
  if (publishing) waiting_stack(oak_timing::clock_ns()-before);
  return result;
}
extern "C" int nanosleep(const timespec *duration, timespec *remaining) {
  using Function = int (*)(const timespec *, timespec *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "nanosleep"));
  auto before = publishing ? oak_timing::clock_ns() : 0;
  int result = original(duration, remaining);
  if (publishing) waiting_stack(oak_timing::clock_ns()-before);
  return result;
}
extern "C" int sem_timedwait(sem_t *semaphore, const timespec *timeout) {
  using Function = int (*)(sem_t *, const timespec *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "sem_timedwait"));
  auto before = publishing ? oak_timing::clock_ns() : 0;
  int result = original(semaphore, timeout);
  if (publishing) waiting_stack(oak_timing::clock_ns()-before);
  return result;
}
extern "C" rcl_ret_t rcl_take(const rcl_subscription_t *sub, void *msg,
                               rmw_message_info_t *info, rmw_subscription_allocation_t *allocation) {
  using Function = rcl_ret_t (*)(const rcl_subscription_t *, void *, rmw_message_info_t *, rmw_subscription_allocation_t *);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT, "rcl_take"));
  auto result = original(sub, msg, info, allocation);
  const char *topic = rcl_subscription_get_topic_name(sub);
  if (result == RCL_RET_OK && relevant(topic)) ros_record("dds_take", topic, msg, info);
  return result;
}
bool gz::transport::v13::Node::Publisher::Publish(const google::protobuf::Message &msg) {
  using Function = bool (*)(void *, const google::protobuf::Message &);
  static auto original = reinterpret_cast<Function>(dlsym(RTLD_NEXT,
    "_ZN2gz9transport3v134Node9Publisher7PublishERKN6google8protobuf7MessageE"));
  auto twist = dynamic_cast<const gz::msgs::Twist *>(&msg);
  std::string fields;
  if (twist) {
    fields = ",\"issued_ns\":"+std::to_string(
      static_cast<long long>(twist->header().stamp().sec())*1000000000LL+twist->header().stamp().nsec())+
      ",\"vx\":"+std::to_string(twist->linear().x())+",\"wz\":"+std::to_string(twist->angular().z());
    for (const auto &item : twist->header().data()) {
      if (item.key() == "frame_id" && item.value_size() == 1) {
        const auto &frame = item.value(0);
        if (frame.find_first_not_of("oak-boottimev1/0123456789abcdef-") == std::string::npos)
          fields += ",\"frame_id\":\""+frame+"\"";
      }
    }
    oak_timing::record("gz_publish_begin", fields.c_str());
  }
  bool result = original(this, msg);
  if (twist) oak_timing::record("gz_publish_end", fields.c_str());
  return result;
}
