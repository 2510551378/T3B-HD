// Execute the production reader/kernel on the original 28-packet actor.
#include "T3BGESeries.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
int main(int argc,char** argv) {
    try {
        if(argc!=4)return 2;
        std::ifstream input(argv[1],std::ios::binary);
        if(!input)throw std::runtime_error("Actor input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(input)),{});
        const auto series=T3BGE::LoadSeries(bytes,28);
        std::ofstream output(argv[2],std::ios::binary),uv(argv[3],std::ios::binary);
        if(!output||!uv)throw std::runtime_error("Actor output not writable");
        std::size_t count=0;
        for(std::size_t i=0;i<series.SampleCount();++i)for(const auto& v:T3BGE::EvaluateSample(series,i)) {
            output.write(reinterpret_cast<const char*>(v.transform.worldPosition.data()),12);
            output.write(reinterpret_cast<const char*>(v.transform.unitWorldNormal.data()),12);
            output.write(reinterpret_cast<const char*>(v.colors.primary.data()),4);
            output.write(reinterpret_cast<const char*>(v.colors.secondary.data()),3);output.put(0);
            uv.write(reinterpret_cast<const char*>(v.uv.data()),8);++count;
        }
        output.close();uv.close();
        if(!output||!uv)throw std::runtime_error("Actor write failed");
        std::cout<<"{\"samples\":"<<series.SampleCount()<<",\"vertices\":"<<count<<"}\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
