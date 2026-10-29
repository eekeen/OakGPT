#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

// Linux-only optional observation. Each bounded JSON record is one append to a
// per-process native filesystem file. No ROS/Gazebo publication from this path.
namespace oak_timing {
inline unsigned long long clock_ns(clockid_t id = CLOCK_BOOTTIME) {
  timespec t{};
  clock_gettime(id, &t);
  return static_cast<unsigned long long>(t.tv_sec)*1000000000ULL+t.tv_nsec;
}
inline void record(const char *stage, const char *detail = "") {
  static int fd = [] {
    const char *root = std::getenv("OAK_TIMING_DIR");
    if (!root || !*root) return -1;
    std::string name = std::string(root)+"/native-"+std::to_string(getpid())+".jsonl";
    return open(name.c_str(), O_WRONLY|O_CREAT|O_APPEND|O_CLOEXEC, 0600);
  }();
  if (fd < 0) return;
  char buffer[2048];
  int n = std::snprintf(buffer, sizeof(buffer),
      "{\"stage\":\"%s\",\"boot_ns\":%llu,\"mono_ns\":%llu,\"thread_cpu_ns\":%llu,\"pid\":%d,\"tid\":%ld%s}\n",
      stage, clock_ns(), clock_ns(CLOCK_MONOTONIC), clock_ns(CLOCK_THREAD_CPUTIME_ID),
      getpid(), syscall(SYS_gettid), detail);
  if (n > 0 && n < static_cast<int>(sizeof(buffer))) {
    auto ignored = write(fd, buffer, static_cast<size_t>(n));
    (void)ignored;
  }
}
}  // namespace oak_timing
