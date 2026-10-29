#include "gazebo_message.hpp"
#include <cstdlib>
#include <iostream>

int main() {
  using namespace oak_expiry;
  int checks = 0;
  auto require = [&checks](bool value) { ++checks; if (!value) std::abort(); };
  gz::msgs::Twist valid;
  auto *frame = valid.mutable_header()->add_data();
  frame->set_key("frame_id");
  frame->add_value("oak-boottime-v1/" + std::string(32, 'a') + "/1");
  valid.mutable_header()->mutable_stamp()->set_sec(1);
  valid.mutable_linear()->set_x(.1);
  Decoded decoded;
  require(decode_message(valid, decoded));
  require(decoded.issued == 1000000000 && decoded.sequence == 1 && decoded.command[0] == .1);
  for (int kind = 0; kind < 7; ++kind) {
    auto bad = valid;
    if (kind == 0) bad.mutable_header()->add_data()->set_key("frame_id");
    if (kind == 1) bad.mutable_header()->mutable_data(0)->add_value("duplicate");
    if (kind == 2) bad.mutable_header()->mutable_stamp()->set_nsec(1000000000);
    if (kind == 3) bad.mutable_header()->mutable_stamp()->set_sec(-1);
    if (kind == 4) bad.mutable_header()->clear_stamp();
    if (kind == 5) bad.mutable_header()->clear_data();
    if (kind == 6) bad.mutable_header()->mutable_data(0)->set_value(0, "invalid");
    require(!decode_message(bad, decoded));
  }
  std::cout << checks << " Gazebo leased-message checks passed\n";
}
