#include "expiry.hpp"
#include <cstdlib>
#include <iostream>
#include <random>

int checks = 0;
void require(bool result) { ++checks; if (!result) std::abort(); }
int main() {
  using namespace oak_expiry;
  const std::string epoch(32, 'a');
  const Command moving{.1,0,0,0,0,.2};
  std::string decoded;
  std::uint64_t sequence = 0;
  require(decode_frame("oak-boottime-v1/"+epoch+"/1", decoded, sequence));
  require(decoded == epoch && sequence == 1);
  for (const auto &invalid : std::array<std::string, 4>{"", "oak-boottime-v1/x/1", "oak-boottime-v1/"+epoch+"/0",
                              "oak-boottime-v1/"+epoch+"/18446744073709551616"}) {
    require(!decode_frame(invalid, decoded, sequence));
  }
  Expiry state;
  require(!state.accept(epoch, 1, 500000000, 1000000000, {}));
  require(!state.latched());
  require(state.tick(1000000000)[0] == 0);
  require(state.accept(epoch, 1, 1000000000, 1000000000, moving));
  require(state.tick(1100000000)[0] == .1);
  require(state.accept(epoch, 2, 1000000000, 1150000000, moving)); // republication cannot renew age
  require(state.tick(1200000000)[0] == 0 && state.latched());
  require(!state.accept(epoch, 3, 1200000000, 1200000000, moving));
  for (int fault = 0; fault < 7; ++fault) {
    Expiry policy;
    require(policy.accept(epoch, 1, 1000000000, 1000000000, moving));
    policy.tick(1000000000);
    if (fault == 0) policy.accept(epoch, 1, 1010000000, 1010000000, moving);
    if (fault == 1) policy.accept(std::string(32, 'b'), 2, 1010000000, 1010000000, moving);
    if (fault == 2) policy.accept(epoch, 2, 1010000000, 1010000000, {1,0,0,0,0,0});
    if (fault == 3) policy.accept(epoch, 2, 1010000000, 1010000000,
                                {std::numeric_limits<double>::quiet_NaN(),0,0,0,0,0});
    if (fault == 4) policy.accept(epoch, 2, 900000000, 1150000000, moving);
    if (fault == 5) policy.accept(epoch, 2, 1500000000, 1100000000, moving);
    if (fault == 6) policy.tick(900000000);
    require(policy.latched() && policy.tick(1150000000)[0] == 0);
  }
  Expiry stalled;
  require(stalled.accept(epoch, 1, 1000000000, 1000000000, moving));
  stalled.tick(1000000000);
  require(stalled.accept(epoch, 2, 2000000000, 2000000000, moving) == false);
  require(stalled.tick(2000000000)[0] == 0);
  Expiry physics_gap;
  require(physics_gap.accept(epoch, 1, 1000000000, 1000000000, moving));
  physics_gap.tick(1000000000);
  require(physics_gap.accept(epoch, 2, 1100000000, 1100000000, moving));
  require(physics_gap.accept(epoch, 3, 1250000000, 1250000000, {}));
  require(physics_gap.tick(1250000000)[0] == 0 && physics_gap.latched());
  require(physics_gap.reason() == "update_gap");
  std::mt19937_64 random(32);
  for (int i = 0; i < 5000; ++i) {
    Expiry policy;
    const std::uint64_t issued = 1000000000, age = random()%400000000;
    const bool accepted = policy.accept(epoch, 1, issued, issued+age, moving);
    require(accepted == (age < lifetime_ns));
    const auto command = policy.tick(issued+age);
    require(command[0] == (accepted ? .1 : 0));
    require(policy.tick(issued+500000000)[0] == 0);
  }
  std::cout << checks << " expiry state/boundary/property checks passed\n";
}
