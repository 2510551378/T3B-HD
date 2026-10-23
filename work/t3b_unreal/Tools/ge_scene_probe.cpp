#include "T3BGEScene.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
std::vector<std::uint8_t> ReadSceneFile(const char* path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Input unreadable");return {std::istreambuf_iterator<char>(f),{}};}
void SaveSceneFile(const char* path,const std::vector<std::uint8_t>& b){std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),b.size());if(!f)throw std::runtime_error("Output failed");}
void Word(std::vector<std::uint8_t>& b,std::uint32_t w){for(unsigned k=0;k<4;++k)b.push_back(static_cast<std::uint8_t>(w>>(k*8)));}
void Floats(std::vector<std::uint8_t>& b,const float* p,std::size_t n){for(std::size_t i=0;i<n;++i){std::uint32_t w;std::memcpy(&w,p+i,4);Word(b,w);}}
int main(int argc,char** argv){
    try{
        if(argc!=4)return 2;
        const auto scene=T3BGE::LoadSceneGeometry(ReadSceneFile(argv[1]));const auto effects=T3BGE::LoadSceneEffectBindings(ReadSceneFile(argv[2]));
        std::vector<std::uint8_t> bytes={'T','3','B','S','F','C','1',0};Word(bytes,scene.width);Word(bytes,scene.height);Word(bytes,scene.frames.size());Word(bytes,scene.atlases.size());
        for(const auto& t:scene.atlases){Word(bytes,t.width);Word(bytes,t.height);bytes.insert(bytes.end(),t.rgba.begin(),t.rgba.end());}
        std::size_t vertices=0,draws=0,colorDraws=0;
        for(std::uint32_t i=0;i<scene.frames.size();++i){
            const auto frame=T3BGE::EvaluateSceneFrame(scene,i,&effects);Word(bytes,frame.sample);Word(bytes,frame.draws.size());
            for(const auto& d:frame.draws){Word(bytes,d.texture);Word(bytes,d.ordinal);Word(bytes,d.flags);Word(bytes,d.vertices.size());Word(bytes,d.stencilRef);
                Floats(bytes,d.localToClip.data(),16);Floats(bytes,d.fog.data(),4);for(auto w:d.fogRGB)Word(bytes,w);
                for(const auto& v:d.vertices){Floats(bytes,v.position,3);Floats(bytes,v.uv,2);Floats(bytes,v.color,4);}vertices+=d.vertices.size();++draws;if(d.flags&4096)++colorDraws;
            }
        }
        SaveSceneFile(argv[3],bytes);std::cout<<"{\"frames\":"<<scene.frames.size()<<",\"atlases\":"<<scene.atlases.size()<<",\"draws\":"<<draws<<",\"vertices\":"<<vertices<<",\"color_draws\":"<<colorDraws<<"}\n";return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
