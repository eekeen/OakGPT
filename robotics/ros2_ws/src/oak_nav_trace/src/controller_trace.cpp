#include "../../../../timing/trace.hpp"
#include <nav2_regulated_pure_pursuit_controller/regulated_pure_pursuit_controller.hpp>
#include <pluginlib/class_list_macros.hpp>
namespace oak_nav_trace {
class ControllerTrace : public nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController {
 public:
  geometry_msgs::msg::TwistStamped computeVelocityCommands(
      const geometry_msgs::msg::PoseStamped &pose, const geometry_msgs::msg::Twist &velocity,
      nav2_core::GoalChecker *checker) override {
    oak_timing::record("controller_compute_begin");
    auto result = RegulatedPurePursuitController::computeVelocityCommands(pose, velocity, checker);
    char fields[160];
    std::snprintf(fields, sizeof(fields), ",\"vx\":%.9g,\"wz\":%.9g,\"sim_ns\":%lld",
      result.twist.linear.x, result.twist.angular.z,
      static_cast<long long>(result.header.stamp.sec)*1000000000LL+result.header.stamp.nanosec);
    oak_timing::record("controller_created", fields);
    return result;
  }
};
}
PLUGINLIB_EXPORT_CLASS(oak_nav_trace::ControllerTrace, nav2_core::Controller)
