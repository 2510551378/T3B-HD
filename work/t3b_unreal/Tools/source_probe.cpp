#include "../Source/T3BRemake/Private/T3BSourceData.h"

#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <string>

namespace {
std::vector<std::uint8_t> ReadFile(const std::string& path) {
    std::ifstream file(path,std::ios::binary);if(!file)throw std::runtime_error("cannot open source input");
    return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(file),{});
}
std::uint32_t Bits(float value) { std::uint32_t result;std::memcpy(&result,&value,4);return result; }
void Point(std::ostream& stream,T3BSource::Vec3 point) { stream<<point.x<<','<<point.y<<','<<point.z; }
}
int main(int argc,char** argv) {
    try {
        std::string mode,input,output;
        for(int index=1;index<argc;index++) {
            const std::string option=argv[index];
            if((option=="--scene"||option=="--skin")&&index+1<argc&&mode.empty()){mode=option;input=argv[++index];}
            else if(option=="--out"&&index+1<argc&&output.empty())output=argv[++index];
            else throw std::runtime_error("usage: source_probe (--scene file | --skin file) --out csv");
        }
        if(mode.empty()||output.empty())throw std::runtime_error("usage: source_probe (--scene file | --skin file) --out csv");
        const auto bytes=ReadFile(input);std::ofstream out(output,std::ios::binary);if(!out)throw std::runtime_error("cannot open CSV output");out<<std::setprecision(9);
        if(mode=="--scene") {
            const auto scene=T3BSource::LoadScene(bytes);
            out<<"sample,index,x,y,z,pc_x,pc_y,pc_z,ue_x,ue_y,ue_z,draw,material,u,v,r,g,b,a,xbits,ybits,zbits,ubits,vbits\n";
            for(std::size_t draw=0;draw<scene.draws.size();draw++) {
                const auto& packet=scene.draws[draw];
                for(std::uint32_t index=packet.first;index<packet.first+packet.count;index++) {
                    const auto& vertex=scene.vertices[index];out<<0<<','<<index<<',';Point(out,vertex.position);out<<',';Point(out,vertex.position);out<<',';Point(out,T3BSource::ToUE(vertex.position));
                    out<<','<<draw<<','<<packet.material<<','<<vertex.uv.u<<','<<vertex.uv.v;
                    for(auto value:vertex.rgba)out<<','<<unsigned(value);
                    out<<','<<Bits(vertex.position.x)<<','<<Bits(vertex.position.y)<<','<<Bits(vertex.position.z)<<','<<Bits(vertex.uv.u)<<','<<Bits(vertex.uv.v)<<'\n';
                }
            }
            std::cout<<"scene_draws="<<scene.draws.size()<<"\nscene_vertices="<<scene.vertices.size()<<"\nscene_materials="<<scene.materials<<'\n';
        } else {
            const auto skin=T3BSource::LoadSkin(bytes);out<<"sample,index,x,y,z,pc_x,pc_y,pc_z,ue_x,ue_y,ue_z,time\n";
            for(std::size_t sample=0;sample<skin.time.size();sample++) {
                const auto posed=T3BSource::PoseOriginal(skin,skin.time[sample]);
                for(std::size_t index=0;index<posed.size();index++) {
                    const auto pc=T3BSource::ToPC(skin,posed[index],0,0,0);out<<sample<<','<<index<<',';Point(out,posed[index]);out<<',';Point(out,pc);out<<',';Point(out,T3BSource::ToUE(pc));out<<','<<skin.time[sample]<<'\n';
                }
            }
            std::cout<<"skin_bones="<<skin.bones<<"\nskin_vertices="<<skin.vertices.size()<<"\nskin_packets="<<skin.packets.size()<<"\nskin_samples="<<skin.time.size()<<'\n';
        }
        out.flush();if(!out)throw std::runtime_error("CSV output write failed");return 0;
    } catch(const std::exception& error) { std::cerr<<"source_probe: "<<error.what()<<'\n';return 2; }
}
