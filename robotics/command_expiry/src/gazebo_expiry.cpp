#include "expiry.hpp"
#include "gazebo_message.hpp"
#include <gz/msgs/stringmsg.pb.h>
#include <gz/msgs/twist.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
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
                     public gz::sim::ISystemPreUpdate {
 public:
  void Configure(const gz::sim::Entity &, const std::shared_ptr<const sdf::Element> &,
                 gz::sim::EntityComponentManager &, gz::sim::EventManager &) override {
    output_ = node_.Advertise<gz::msgs::Twist>("/oak/actuator_cmd");
    events_ = node_.Advertise<gz::msgs::StringMsg>("/oak/expiry_events");
    node_.Subscribe("/oak/leased_cmd_vel", &GazeboExpiry::receive, this);
  }
  void receive(const gz::msgs::Twist &message) {
    std::lock_guard<std::mutex> lock(mutex_);
    Decoded decoded;
    if (!decode_message(message, decoded)) {
      policy_.reject("invalid_header"); return;
    }
    policy_.accept(decoded.epoch, decoded.sequence, decoded.issued, boottime(), decoded.command);
  }
  void PreUpdate(const gz::sim::UpdateInfo &info, gz::sim::EntityComponentManager &) override {
    const auto now = boottime();
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
    if (reason != last_reason_ || now-last_event_ >= 1000000000) {
      std::ostringstream text;
      text << "{\"reason\":\"" << reason << "\",\"latched\":" << (latched ? "true" : "false")
           << ",\"boottime_ns\":" << now << ",\"lifetime_ns\":" << lifetime_ns
           << ",\"sim_ns\":" << info.simTime.count() << "}";
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
};
}  // namespace oak_expiry
GZ_ADD_PLUGIN(oak_expiry::GazeboExpiry, gz::sim::System,
              oak_expiry::GazeboExpiry::ISystemConfigure,
              oak_expiry::GazeboExpiry::ISystemPreUpdate)
