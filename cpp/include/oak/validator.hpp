#pragma once
#include <cstdint>
#include <string>
#include <nlohmann/json.hpp>

namespace oak {
using Json = nlohmann::json;
Json strict_parse(const std::string& input);
Json authorized_steps(const std::string& instruction);
Json validate(const std::string& input, const Json& policy, std::int64_t now_ms) noexcept;
}
