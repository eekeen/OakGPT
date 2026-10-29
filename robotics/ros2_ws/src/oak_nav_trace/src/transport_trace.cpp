#include "../../../../timing/trace.hpp"
#include <dlfcn.h>
#include <rcl/publisher.h>
#include <rcl/subscription.h>
#include <gz/transport/Node.hh>
#include <gz/msgs/twist.pb.h>
#include <geometry_msgs/msg/twist_stamped.hpp>

namespace {
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
  if (relevant(topic)) ros_record("dds_publish_begin", topic, msg);
  auto result = original(publisher, msg, allocation);
  if (relevant(topic)) ros_record("dds_publish_end", topic);
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
