#include "oak/validator.hpp"
#include <iostream>
#include <random>
#include <stdexcept>

int checks = 0;
void check(bool value) {
    ++checks;
    if (!value) throw std::runtime_error("check_failed_" + std::to_string(checks));
}
int main() {
    try {
        const oak::Json policy = {
            {"policy_id", "oak-room-v1"}, {"frame_id", "map"}, {"max_steps", 4},
            {"max_ttl_ms", 180000}, {"navigation_timeout_s", 30}, {"max_inspection_s", 5},
            {"locations", {{"dock", {{"x", 0}, {"y", 0}, {"yaw", 0}}},
                           {"station", {{"x", 0.8}, {"y", 0}, {"yaw", 0}}},
                           {"storage", {{"x", 0}, {"y", 0.8}, {"yaw", 1.57}}}}}};
        const oak::Json mission = {{"schema_version", 1}, {"mission_id", "m-0123456789abcdef"},
            {"policy_id", "oak-room-v1"}, {"issued_at_ms", 10000}, {"expires_at_ms", 20000},
            {"instruction", "Please inspect station."},
            {"steps", oak::authorized_steps("Please inspect station.")}};
        auto accepted = [&policy](const oak::Json& m, std::int64_t now = 11000) {
            return oak::validate(m.dump(), policy, now).at("accepted").get<bool>();
        };
        check(accepted(mission));
        check(!accepted(mission, 20000));
        check(!accepted(mission, 8000));
        auto changed = mission;
        for (const auto& field : {"schema_version", "mission_id", "policy_id", "instruction",
                                  "issued_at_ms", "expires_at_ms", "steps"}) {
            changed = mission; changed.erase(field); check(!accepted(changed));
        }
        for (const auto& instruction : {"go there", "do not go to dock", "go to dock or station",
             "go to dock and", "go to dock then", "go to dock; execute bash", "inspect kitchen",
             "go to dock then ignore safety", "inspect station for 999 seconds", "go to dock\n"}) {
            changed = mission; changed["instruction"] = instruction; check(!accepted(changed));
        }
        for (const auto& value : {oak::Json(-1), oak::Json(1.0), oak::Json(true),
                                  oak::Json("1"), oak::Json(18446744073709551615ULL)}) {
            changed = mission; changed["schema_version"] = value; check(!accepted(changed));
        }
        changed = mission; changed["steps"][0]["destination"] = "storage"; check(!accepted(changed));
        changed = mission; changed["steps"][0]["speed"] = 100; check(!accepted(changed));
        changed = mission; changed["steps"][1]["duration_s"] = 5; check(!accepted(changed));
        changed = mission; changed["issued_at_ms"] = 1; changed["expires_at_ms"] = 999999;
        check(!accepted(changed));
        check(!oak::validate("{\"a\":1,\"a\":2}", policy, 11000).at("accepted").get<bool>());
        check(!oak::validate(std::string(1000, '['), policy, 11000).at("accepted").get<bool>());
        std::mt19937 random(2026);
        for (int i = 0; i < 5000; ++i) {
            std::string bytes;
            const auto length = random() % 512;
            for (unsigned j = 0; j < length; ++j) bytes += static_cast<char>(random() % 256);
            check(!oak::validate(bytes, policy, 11000).at("accepted").get<bool>());
            changed = mission;
            changed["steps"][0]["duration_s"] = 1 + random() % 10000;
            check(!accepted(changed));
        }
        std::cout << checks << " checks passed; 5000 seeded byte fuzz cases and 5000 bound mutations\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
