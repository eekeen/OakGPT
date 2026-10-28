#include <cmath>
#include <memory>
#include <sstream>
#include <string>
#include "nav2_controller/plugins/simple_progress_checker.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "std_msgs/msg/string.hpp"

namespace oak_nav_trace {
class ProgressTrace : public nav2_controller::SimpleProgressChecker {
 public:
  void initialize(const rclcpp_lifecycle::LifecycleNode::WeakPtr &parent,
                  const std::string &name) override {
    SimpleProgressChecker::initialize(parent, name);
    // A regular publisher works while the parent transitions lifecycle states.
    publisher_ = rclcpp::create_publisher<std_msgs::msg::String>(
        parent.lock(), "/oak/progress_state", rclcpp::QoS(100));
  }
  bool check(geometry_msgs::msg::PoseStamped &pose) override {
    const bool accepted = SimpleProgressChecker::check(pose);
    const double distance = std::hypot(pose.pose.position.x - baseline_pose_.x,
                                       pose.pose.position.y - baseline_pose_.y);
    std::ostringstream data;
    data.precision(17);
    data << "{\"check\":" << (accepted ? "true" : "false")
         << ",\"sim_ns\":" << clock_->now().nanoseconds()
         << ",\"baseline_ns\":" << baseline_time_.nanoseconds()
         << ",\"baseline_x\":" << baseline_pose_.x
         << ",\"baseline_y\":" << baseline_pose_.y
         << ",\"x\":" << pose.pose.position.x << ",\"y\":" << pose.pose.position.y
         << ",\"distance_m\":" << distance << ",\"radius_m\":" << radius_
         << ",\"allowance_s\":" << time_allowance_.seconds() << "}";
    std_msgs::msg::String message;
    message.data = data.str();
    publisher_->publish(message);
    return accepted;
  }
 private:
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
};
}  // namespace oak_nav_trace
PLUGINLIB_EXPORT_CLASS(oak_nav_trace::ProgressTrace, nav2_core::ProgressChecker)
