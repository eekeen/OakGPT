// Diagnostic-only ABI probe for the recorded ROS Jazzy/Fast DDS installation.
// No navigation clients, actuator publishers, or mission authorization changes.
#include <cstring>
#include <iostream>
#include <rcl/service.h>
#include <rclcpp/rclcpp.hpp>
#include <rmw_fastrtps_shared_cpp/custom_service_info.hpp>
#include <std_srvs/srv/trigger.hpp>

int main(int argc, char **argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("oak_service_qos_probe");
  auto service = node->create_service<std_srvs::srv::Trigger>("oak/qos_probe",
    [](const std::shared_ptr<std_srvs::srv::Trigger::Request>,
       std::shared_ptr<std_srvs::srv::Trigger::Response> response) { response->success = true; });
  const auto *handle = rcl_service_get_rmw_handle(service->get_service_handle().get());
  if (!handle || std::strcmp(handle->implementation_identifier, "rmw_fastrtps_cpp") != 0) {
    std::cerr << "Probe requires the recorded rmw_fastrtps_cpp implementation\n";
    rclcpp::shutdown(); return 2;
  }
  const auto qos = static_cast<CustomServiceInfo *>(handle->data)->response_writer_->get_qos();
  const auto duration = qos.reliability().max_blocking_time;
  std::cout << "{\"service_response_max_blocking_seconds\":" << duration.seconds
            << ",\"nanoseconds\":" << duration.nanosec << "}\n";
  const bool expected = duration.seconds == 1 && duration.nanosec == 0;
  service.reset(); node.reset(); rclcpp::shutdown();
  return expected ? 0 : 1;
}
