#pragma once
#include "expiry.hpp"
#include <gz/msgs/twist.pb.h>

namespace oak_expiry {
struct Decoded {
  std::string epoch;
  std::uint64_t sequence{0}, issued{0};
  Command command{};
};
inline bool decode_message(const gz::msgs::Twist &message, Decoded &output) {
  int frames = 0;
  std::string frame;
  for (const auto &entry : message.header().data()) {
    if (entry.key() == "frame_id") {
      if (++frames != 1 || entry.value_size() != 1) return false;
      frame = entry.value(0);
    }
  }
  const auto &stamp = message.header().stamp();
  if (frames != 1 || !decode_frame(frame, output.epoch, output.sequence) ||
      stamp.sec() < 0 || stamp.sec() > 10000000000LL ||
      stamp.nsec() < 0 || stamp.nsec() >= 1000000000) return false;
  output.issued = static_cast<std::uint64_t>(stamp.sec())*1000000000 +
                  static_cast<std::uint64_t>(stamp.nsec());
  if (output.issued == 0) return false;
  output.command = {message.linear().x(), message.linear().y(), message.linear().z(),
                    message.angular().x(), message.angular().y(), message.angular().z()};
  return true;
}
}  // namespace oak_expiry
