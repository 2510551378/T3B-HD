#include "T3BGEEffectClock.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

int main(int argc,char** argv) {
    try {
        if (argc!=3) return 2;
        std::ifstream in(argv[1],std::ios::binary);
        if (!in) throw std::runtime_error("Clock input not readable");
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
        if (bytes.size()<12 || bytes.size()>1024*1024 || std::memcmp(bytes.data(),"T3BCLK1\0",8))
            throw std::runtime_error("Wrong clock transport");
        std::size_t at=8;
        const auto word=[&]() {
            if (bytes.size()-at<4) throw std::runtime_error("Truncated clock operation");
            const auto* p=bytes.data()+at;at+=4;
            return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
        };
        const auto number=[&]() {auto bits=word();float f;std::memcpy(&f,&bits,4);return f;};
        const auto n=word();if (!n||n>4096) throw std::runtime_error("Clock operation count bound");
        std::ofstream out(argv[2],std::ios::binary);
        for (std::uint32_t i=0;i<n;++i) {
            const auto kind=word();const float a=number(),b=number();const auto x=word(),y=word();float result;
            if (kind==0) result=T3BGE::AdvanceOriginalEffectTime(a,b);
            else if (kind==1) {
                if(x>65535||y>65535)throw std::runtime_error("Loop interval outside u16");
                result=T3BGE::WrapOriginalEffectTime(a,static_cast<std::uint16_t>(x),static_cast<std::uint16_t>(y));
            } else if (kind==2) {
                std::int32_t signedY;std::memcpy(&signedY,&y,4);
                if(x>1||signedY<-32768||signedY>32767)throw std::runtime_error("Invalid original time-slot input");
                result=T3BGE::RelativeOriginalEffectTime(a,x!=0,static_cast<std::int16_t>(signedY));
            } else throw std::runtime_error("Unsupported clock operation");
            out.write(reinterpret_cast<const char*>(&result),4);
        }
        if(at!=bytes.size())throw std::runtime_error("Trailing clock bytes");
        out.close();if(!out)throw std::runtime_error("Clock output failed");
        std::cout<<"{\"operations\":"<<n<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
