#include "../Source/T3BRemake/Private/T3BActionClip.h"

#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

static std::vector<std::uint8_t> Read(const char* path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unreadable action clip");
    return {std::istreambuf_iterator<char>(in), {}};
}

int main(int argc, char** argv) {
    try {
        if (argc != 3) return 2;
        auto pair = T3BAction::LoadSynchronizedPair(Read(argv[1]), Read(argv[2]));
        std::cout << "{\"bodyBones\":" << pair.body.bones
                  << ",\"bodyVertices\":" << pair.body.vertices.size()
                  << ",\"weaponBones\":" << pair.weapon.bones
                  << ",\"weaponVertices\":" << pair.weapon.vertices.size()
                  << ",\"samples\":" << pair.body.time.size()
                  << ",\"duration\":" << pair.body.time.back() << "}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
