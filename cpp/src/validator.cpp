#include "oak/validator.hpp"
#include <algorithm>
#include <cmath>
#include <regex>
#include <set>
#include <stdexcept>
#include <vector>

namespace oak {
namespace {
void require(bool condition, const std::string& reason) {
    if (!condition) throw std::invalid_argument(reason);
}
void keys(const Json& value, const std::set<std::string>& expected) {
    require(value.is_object(), "object_required");
    std::set<std::string> actual;
    for (auto it = value.begin(); it != value.end(); ++it) actual.insert(it.key());
    require(actual == expected, "unexpected_or_missing_fields");
}
std::int64_t integer(const Json& value, std::int64_t low, std::int64_t high) {
    require(value.is_number_integer() && value >= low && value <= high, "integer_out_of_bounds");
    return value.get<std::int64_t>();
}
std::string text(const Json& value) {
    require(value.is_string(), "string_required");
    return value.get<std::string>();
}
std::string normalized(const std::string& input) {
    require(!input.empty() && input.size() <= 256, "instruction_size");
    std::string result;
    bool space = false;
    for (unsigned char c : input) {
        require(c >= 32 && c < 127, "instruction_ascii_required");
        if (c == ' ') { space = !result.empty(); continue; }
        if (space) { result += ' '; space = false; }
        result += static_cast<char>(c >= 'A' && c <= 'Z' ? c + 32 : c);
    }
    if (!result.empty() && result.back() == '.') result.pop_back();
    require(!result.empty(), "instruction_empty");
    return result;
}
void policy_valid(const Json& policy) {
    keys(policy, {"policy_id", "frame_id", "max_steps", "max_ttl_ms",
                  "navigation_timeout_s", "max_inspection_s", "locations"});
    require(text(policy.at("policy_id")) == "oak-room-v1", "policy_version");
    require(text(policy.at("frame_id")) == "map", "policy_frame");
    integer(policy.at("max_steps"), 1, 4);
    integer(policy.at("max_ttl_ms"), 1000, 180000);
    integer(policy.at("navigation_timeout_s"), 1, 30);
    integer(policy.at("max_inspection_s"), 1, 5);
    keys(policy.at("locations"), {"dock", "station", "storage"});
    for (const auto& pose : policy.at("locations")) {
        keys(pose, {"x", "y", "yaw"});
        for (const auto& name : {"x", "y", "yaw"}) {
            require(pose.at(name).is_number(), "policy_pose_number");
            const double value = pose.at(name).get<double>();
            require(std::isfinite(value) && std::abs(value) <=
                    (std::string(name) == "yaw" ? 3.141592653589793 : 1.5), "policy_pose_bounds");
        }
    }
}
}

Json strict_parse(const std::string& input) {
    require(input.size() <= 16384, "payload_size");
    std::vector<std::set<std::string>> objects;
    auto callback = [&objects](int depth, Json::parse_event_t event, Json& value) {
        require(depth <= 16, "json_depth_limit");
        if (event == Json::parse_event_t::object_start) objects.emplace_back();
        if (event == Json::parse_event_t::key)
            require(objects.back().insert(value.get<std::string>()).second, "duplicate_key");
        if (event == Json::parse_event_t::object_end) objects.pop_back();
        return true;
    };
    return Json::parse(input, callback, true, false);
}

Json authorized_steps(const std::string& instruction) {
    std::string remaining = normalized(instruction);
    // Full-clause matching rejects negation, alternatives, extra clauses and injected code.
    const std::regex clause(
        R"(^(?:please )?(go to|navigate to|visit|move to|head to|travel to|proceed to|inspect|check|examine) (dock|charging dock|station|inspection station|storage|storage bay)$)");
    Json steps = Json::array();
    while (!remaining.empty()) {
        std::size_t separator = remaining.find(" then ");
        std::string part = separator == std::string::npos ? remaining : remaining.substr(0, separator);
        if (separator != std::string::npos && part.size() > 4 &&
            part.substr(part.size()-4) == " and") part.resize(part.size()-4);
        std::smatch match;
        require(std::regex_match(part, match, clause), "instruction_not_authorized");
        const std::string verb = match[1].str();
        std::string destination = match[2].str();
        if (destination == "charging dock") destination = "dock";
        if (destination == "inspection station") destination = "station";
        if (destination == "storage bay") destination = "storage";
        steps.push_back({{"action", "navigate"}, {"destination", destination}, {"duration_s", 0}});
        if (verb == "inspect" || verb == "check" || verb == "examine")
            steps.push_back({{"action", "inspect"}, {"destination", destination}, {"duration_s", 2}});
        require(steps.size() <= 4, "mission_too_many_steps");
        if (separator == std::string::npos) break;
        remaining = remaining.substr(separator + 6);
        require(!remaining.empty(), "unfinished_instruction");
    }
    return steps;
}

Json validate(const std::string& input, const Json& policy, std::int64_t now_ms) noexcept {
    try {
        policy_valid(policy);
        const Json mission = strict_parse(input);
        keys(mission, {"schema_version", "mission_id", "policy_id", "issued_at_ms",
                       "expires_at_ms", "instruction", "steps"});
        integer(mission.at("schema_version"), 1, 1);
        require(std::regex_match(text(mission.at("mission_id")),
                std::regex("m-[0-9a-f]{16}")), "mission_id");
        require(mission.at("policy_id") == policy.at("policy_id"), "policy_mismatch");
        constexpr std::int64_t max_time = 9007199254740991LL;
        const auto issued = integer(mission.at("issued_at_ms"), 0, max_time);
        const auto expires = integer(mission.at("expires_at_ms"), 0, max_time);
        require(now_ms >= 0 && now_ms < max_time-1000, "clock_bounds");
        require(issued <= now_ms + 1000 && expires > now_ms && expires > issued &&
                expires-issued <= policy.at("max_ttl_ms").get<std::int64_t>(), "mission_expired_or_future");
        const auto& steps = mission.at("steps");
        require(steps.is_array() && !steps.empty() && steps.size() <=
                policy.at("max_steps").get<std::size_t>(), "step_count");
        Json validated = Json::array();
        std::string previous_destination;
        for (const auto& step : steps) {
            keys(step, {"action", "destination", "duration_s"});
            const std::string action = text(step.at("action"));
            const std::string destination = text(step.at("destination"));
            require(policy.at("locations").contains(destination), "destination_not_permitted");
            if (action == "navigate") {
                integer(step.at("duration_s"), 0, 0);
                previous_destination = destination;
            } else {
                require(action == "inspect", "action_not_permitted");
                integer(step.at("duration_s"), 1, policy.at("max_inspection_s").get<int>());
                require(previous_destination == destination, "inspection_requires_navigation");
            }
            Json resolved = step;
            resolved["pose"] = policy.at("locations").at(destination);
            validated.push_back(resolved);
        }
        require(steps == authorized_steps(text(mission.at("instruction"))), "intent_mismatch");
        return {{"accepted", true}, {"reason", "ok"}, {"mission_id", mission.at("mission_id")},
                {"frame_id", policy.at("frame_id")}, {"steps", validated},
                {"navigation_timeout_s", policy.at("navigation_timeout_s")}};
    } catch (const std::exception& error) {
        return {{"accepted", false}, {"reason", error.what()}};
    } catch (...) {
        return {{"accepted", false}, {"reason", "unknown_validation_error"}};
    }
}
}
