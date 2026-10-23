#include "T3BGELighting.h"
#include <iostream>
#include <limits>
#include <stdexcept>

int main() {
    unsigned passed=0,failed=0;
    auto reject=[&](auto action){try{action();++failed;}catch(const std::runtime_error&){++passed;}};
    T3BGE::Registers regs{};T3BGE::V3 p{0,0,0},n{0,0,1};
    reject([&]{T3BGE::Light(regs,p,n);}); // lighting-disabled path needs its own input color contract
    regs[0x17]=1;regs[0x12]=7U<<2;
    reject([&]{T3BGE::Light(regs,p,n);}); // COLOR_0 must not be silently ignored
    regs[0x12]=1U<<23;
    reject([&]{T3BGE::Light(regs,p,n);}); // through mode bypasses this transform pipeline
    regs[0x12]=0;regs[0x18]=1;regs[0x5F]=0x200;
    reject([&]{T3BGE::Light(regs,p,n);}); // unimplemented spot light
    regs[0x5F]=0;p[0]=std::numeric_limits<float>::quiet_NaN();
    reject([&]{T3BGE::Light(regs,p,n);});
    std::array<T3BGE::Matrix43,8> bones{};T3BGE::Matrix43 world{};
    T3BGE::Vertex vertex{};vertex.weights[0]=1;
    reject([&]{T3BGE::Transform(vertex,bones,0,world,false);});
    reject([&]{T3BGE::Transform(vertex,bones,9,world,false);});
    vertex.weights[0]=-1;
    reject([&]{T3BGE::Transform(vertex,bones,1,world,false);});
    std::cout<<"{\"scope_cases_passed\":"<<passed<<",\"scope_cases_failed\":"<<failed<<"}\n";
    return failed?1:0;
}
