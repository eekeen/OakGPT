#include "expiry.hpp"
#include "gazebo_message.hpp"
#include "../../timing/trace.hpp"
#include <gz/msgs/stringmsg.pb.h>
#include <gz/msgs/twist.pb.h>
#include <gz/msgs/contacts.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/ContactSensorData.hh>
#include <gz/transport/Node.hh>
#include <mutex>
#include <sstream>
#include <time.h>

namespace oak_expiry {
std::uint64_t boottime() {
  timespec value{};
  if (clock_gettime(CLOCK_BOOTTIME, &value) != 0) return 0;
  return static_cast<std::uint64_t>(value.tv_sec)*1000000000 +
         static_cast<std::uint64_t>(value.tv_nsec);
}
class GazeboExpiry : public gz::sim::System, public gz::sim::ISystemConfigure,
                     public gz::sim::ISystemPreUpdate, public gz::sim::ISystemPostUpdate {
 public:
  void Configure(const gz::sim::Entity &entity, const std::shared_ptr<const sdf::Element> &,
                 gz::sim::EntityComponentManager &, gz::sim::EventManager &) override {
    entity_ = entity;
    output_ = node_.Advertise<gz::msgs::Twist>("/oak/actuator_cmd");
    events_ = node_.Advertise<gz::msgs::StringMsg>("/oak/expiry_events");
    node_.Subscribe("/oak/leased_cmd_vel", &GazeboExpiry::receive, this);
    for (const char *name : {"base_link_body", "left_wheel_c", "right_wheel_c", "caster_c"}) {
      node_.Subscribe(std::string("/oak/contacts/")+name, &GazeboExpiry::contacts, this);
    }
  }
  void contacts(const gz::msgs::Contacts &message) {
    contacts_at(message, static_cast<long long>(message.header().stamp().sec())*1000000000LL+message.header().stamp().nsec(), "transport");
  }
  void contacts_at(const gz::msgs::Contacts &message, long long sim_ns, const char *source) {
    std::string fields = ",\"count\":"+std::to_string(message.contact_size())+
      ",\"sim_ns\":"+std::to_string(sim_ns)+",\"contact_source\":\""+source+"\"";
    oak_timing::record("contact_sample", fields.c_str());
    for (const auto &contact : message.contact()) {
      // Names are generated locally from fixed, alphanumeric world identifiers.
      auto detail = fields+",\"collision1\":\""+contact.collision1().name()+"\",\"collision2\":\""+contact.collision2().name()+"\"";
      oak_timing::record("contact_pair", detail.c_str());
    }
  }
  void PostUpdate(const gz::sim::UpdateInfo &info, const gz::sim::EntityComponentManager &ecm) override {
    ecm.Each<gz::sim::components::ContactSensorData>(
      [this, &info](const gz::sim::Entity &, const gz::sim::components::ContactSensorData *data) {
        // Physics component messages have no container timestamp; use this
        // PostUpdate's actual simulator time, not a zero/default header.
        contacts_at(data->Data(), static_cast<long long>(info.simTime.count()), "physics_ecm");
        return true;
      });
    if (++pose_tick_ % 4 == 0) {
      auto pose = gz::sim::worldPose(entity_, ecm);
      char fields[256];
      std::snprintf(fields, sizeof(fields), ",\"sim_ns\":%lld,\"x\":%.12g,\"y\":%.12g,\"yaw\":%.12g",
        static_cast<long long>(info.simTime.count()), pose.Pos().X(), pose.Pos().Y(), pose.Rot().Yaw());
      oak_timing::record("ground_truth_native", fields);
    }
  }
  void receive(const gz::msgs::Twist &message) {
    oak_timing::record("native_ingress");
    std::lock_guard<std::mutex> lock(mutex_);
    Decoded decoded;
    if (!decode_message(message, decoded)) {
      policy_.reject("invalid_header"); return;
    }
    char fields[256];
    std::snprintf(fields, sizeof(fields), ",\"sequence\":%llu,\"issued_ns\":%llu,\"vx\":%.9g",
      static_cast<unsigned long long>(decoded.sequence), static_cast<unsigned long long>(decoded.issued), decoded.command[0]);
    oak_timing::record("native_decoded", fields);
    policy_.accept(decoded.epoch, decoded.sequence, decoded.issued, boottime(), decoded.command);
    oak_timing::record("native_ingress_end");
  }
  void PreUpdate(const gz::sim::UpdateInfo &info, gz::sim::EntityComponentManager &) override {
    const auto now = boottime();
    char fields[160];
    std::snprintf(fields, sizeof(fields), ",\"sim_ns\":%lld,\"paused\":%s", static_cast<long long>(info.simTime.count()), info.paused ? "true" : "false");
    oak_timing::record("preupdate_begin", fields);
    Command command{};
    std::string reason;
    bool latched;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      command = policy_.tick(now); reason = policy_.reason(); latched = policy_.latched();
    }
    gz::msgs::Twist message;
    if (!info.paused) {
      message.mutable_linear()->set_x(command[0]);
      message.mutable_angular()->set_z(command[5]);
    }
    output_.Publish(message);
    oak_timing::record("actuator_published", fields);
    if (reason != last_reason_ || now-last_event_ >= 1000000000) {
      std::ostringstream text;
      text << "{\"reason\":\"" << reason << "\",\"latched\":" << (latched ? "true" : "false")
           << ",\"boottime_ns\":" << now << ",\"lifetime_ns\":" << lifetime_ns
           << ",\"sim_ns\":" << info.simTime.count() << "}";
      auto trace_fields = std::string(",\"state\":")+text.str();
      oak_timing::record("expiry_state", trace_fields.c_str());
      gz::msgs::StringMsg event; event.set_data(text.str()); events_.Publish(event);
      last_reason_ = reason; last_event_ = now;
    }
  }
 private:
  gz::transport::Node node_;
  gz::transport::Node::Publisher output_, events_;
  Expiry policy_;
  std::mutex mutex_;
  std::string last_reason_;
  std::uint64_t last_event_{0};
  gz::sim::Entity entity_{};
  unsigned pose_tick_{0};
};
}  // namespace oak_expiry
GZ_ADD_PLUGIN(oak_expiry::GazeboExpiry, gz::sim::System,
              oak_expiry::GazeboExpiry::ISystemConfigure,
              oak_expiry::GazeboExpiry::ISystemPreUpdate,
              oak_expiry::GazeboExpiry::ISystemPostUpdate)
