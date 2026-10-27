#include "oak/validator.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <iterator>

int main(int argc, char** argv) {
    try {
        if (argc != 3 || std::string(argv[1]) != "--policy")
            throw std::invalid_argument("usage: oak-validate --policy trusted-policy.json < mission.json");
        std::ifstream policy_file(argv[2]);
        if (!policy_file) throw std::invalid_argument("policy_unavailable");
        std::string policy_text((std::istreambuf_iterator<char>(policy_file)), {});
        const auto policy = oak::strict_parse(policy_text);
        std::string input;
        char c;
        while (std::cin.get(c)) {
            input += c;
            if (input.size() > 16384) throw std::invalid_argument("payload_size");
        }
        const auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
        const auto result = oak::validate(input, policy, now);
        std::cout << result.dump() << '\n';
        return result.at("accepted").get<bool>() ? 0 : 2;
    } catch (const std::exception& error) {
        std::cout << oak::Json({{"accepted", false}, {"reason", error.what()}}).dump() << '\n';
        return 2;
    }
}
