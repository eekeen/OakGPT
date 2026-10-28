#pragma once
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <string_view>

namespace oak_expiry {
using Command = std::array<double, 6>;
constexpr std::uint64_t lifetime_ns = 200000000;
constexpr std::uint64_t future_tolerance_ns = 20000000;

inline bool decode_frame(std::string_view frame, std::string &epoch, std::uint64_t &sequence) {
  constexpr std::string_view prefix = "oak-boottime-v1/";
  if (frame.size() < prefix.size() + 34 || frame.size() > prefix.size() + 53 ||
      frame.substr(0, prefix.size()) != prefix) return false;
  const auto identity = frame.substr(prefix.size(), 32);
  for (const char c : identity) {
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
  }
  if (frame[prefix.size()+32] != '/') return false;
  const auto value = frame.substr(prefix.size()+33);
  if (value.empty() || value.front() == '0') return false;
  const auto parsed = std::from_chars(value.data(), value.data()+value.size(), sequence);
  if (parsed.ec != std::errc{} || parsed.ptr != value.data()+value.size() || sequence == 0) return false;
  epoch = std::string(identity);
  return true;
}

class Expiry {
 public:
  void reject(const char *reason) {
    if (!latched_) reason_ = reason;
    latched_ = true;
  }
  bool accept(const std::string &epoch, std::uint64_t sequence, std::uint64_t issued,
              std::uint64_t now, const Command &value) {
    if (latched_) return false;
    if (armed_ && now >= deadline_) { reject("command_expired"); return false; }
    bool bounded = true;
    for (const double v : value) bounded = bounded && std::isfinite(v);
    bounded = bounded && std::abs(value[0]) <= .220001 && std::abs(value[5]) <= .800001;
    for (const unsigned index : {1u, 2u, 3u, 4u}) bounded = bounded && std::abs(value[index]) <= 1e-6;
    if (!bounded) { reject("invalid_command"); return false; }
    if (epoch.size() != 32 || sequence == 0 || (!epoch_.empty() &&
        (epoch != epoch_ || sequence <= sequence_))) { reject("identity_or_replay"); return false; }
    // DDS/Gazebo startup can deliver queued neutral commands before physics starts.
    // Discard expired neutral input before arming; never forward it or renew a lease.
    if (!armed_ && value == Command{} && now >= issued && now-issued >= lifetime_ns) {
      reason_ = "discarded_startup_zero"; return false;
    }
    if (issued == 0 || issued > std::numeric_limits<std::uint64_t>::max()-lifetime_ns ||
        (issued > now && issued-now > future_tolerance_ns) ||
        (now >= issued && now-issued >= lifetime_ns)) { reject("invalid_command_age"); return false; }
    epoch_ = epoch; sequence_ = sequence; command_ = value; deadline_ = issued+lifetime_ns;
    if (std::abs(value[0]) > 1e-9 || std::abs(value[5]) > 1e-9) armed_ = true;
    reason_ = armed_ ? "forwarding" : "idle";
    return true;
  }
  Command tick(std::uint64_t now) {
    if (last_tick_ && now < last_tick_) reject("clock_regression");
    else if (armed_ && last_tick_ && now-last_tick_ >= lifetime_ns) reject("update_gap");
    last_tick_ = now;
    if (armed_ && now >= deadline_) reject("command_expired");
    return latched_ || now >= deadline_ ? Command{} : command_;
  }
  bool latched() const { return latched_; }
  const std::string &reason() const { return reason_; }
 private:
  Command command_{};
  std::string epoch_, reason_{"idle"};
  std::uint64_t sequence_{0}, deadline_{0}, last_tick_{0};
  bool armed_{false}, latched_{false};
};
}  // namespace oak_expiry
