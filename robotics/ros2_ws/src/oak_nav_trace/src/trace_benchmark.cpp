#include "../../../../timing/trace.hpp"
#include <algorithm>
#include <iostream>
#include <vector>
int main() {
  std::vector<unsigned long long> times;
  times.reserve(20000);
  for (int i=0; i<20000; ++i) {
    auto before=oak_timing::clock_ns();
    oak_timing::record("overhead_probe", ",\"sequence\":1");
    times.push_back(oak_timing::clock_ns()-before);
  }
  std::sort(times.begin(), times.end());
  std::cout << "{\"samples\":20000,\"median_ns\":" << times[10000]
    << ",\"p99_ns\":" << times[19800] << ",\"max_ns\":" << times.back() << "}\n";
}
