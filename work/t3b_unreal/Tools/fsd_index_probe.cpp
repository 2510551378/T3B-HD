#include "../Source/T3BRemake/Private/T3BFSDIndex.h"

#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

static std::vector<std::uint8_t> Read(const char* path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("unreadable 3rd.fsd");
    return {std::istreambuf_iterator<char>(in), {}};
}

int main(int argc, char** argv) {
    try {
        if (argc != 2) return 2;
        const auto index = T3BFSD::Load(Read(argv[1]));
        std::cout << "{\"version\":" << index.version
                  << ",\"headerBytes\":" << index.headerBytes
                  << ",\"declaredRecordCount\":" << index.declaredRecordCount
                  << ",\"declaredRecordStride\":" << index.declaredRecordStride
                  << ",\"recordStart\":" << index.recordStart
                  << ",\"records\":" << index.records.size()
                  << ",\"sentinel\":" << index.sentinel
                  << ",\"packageSize\":" << index.packageSize << "}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
