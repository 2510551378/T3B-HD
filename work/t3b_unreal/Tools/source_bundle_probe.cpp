#include "T3BSourceData.h"
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<std::uint8_t> Read(const char* path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("source bundle file is missing");
    input.seekg(0, std::ios::end); const auto size=input.tellg(); input.seekg(0, std::ios::beg);
    if (size<0) throw std::runtime_error("source bundle size failed");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    if (!bytes.empty()) input.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (!input && !bytes.empty()) throw std::runtime_error("source bundle read failed");
    return bytes;
}
void Check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
struct SkinStats { std::size_t poses{}; std::size_t points{}; float firstX{},lastX{}; };
SkinStats CheckSkin(const T3BSource::Skin& skin) {
    SkinStats result; result.poses=skin.time.size();
    for (float time:skin.time) {
        const auto posed=T3BSource::PoseOriginal(skin,time); result.points+=posed.size();
        Check(posed.size()==skin.vertices.size(),"source pose vertex count changed");
        for(const auto& p:posed) Check(std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z),"source pose became nonfinite");
        if(result.poses==skin.time.size()) result.lastX=posed.front().x; else if(result.poses>0 && result.points==posed.size()) result.firstX=posed.front().x;
    }
    return result;
}
}

int main(int argc,char** argv){
    try {
        if(argc!=6) return 2;
        const auto scene=T3BSource::LoadScene(Read(argv[1]));
        const auto aya=T3BSource::LoadSkin(Read(argv[2]));
        const auto weapon=T3BSource::LoadSkin(Read(argv[3]));
        const auto twisted=T3BSource::LoadSkin(Read(argv[4]));
        Check(scene.draws.size()==140&&scene.vertices.size()==31656&&scene.materials==81,"unexpected source scene contract");
        Check(aya.bones==44&&aya.packets.size()==106&&aya.vertices.size()==3456&&aya.time.size()==60,"unexpected Aya source contract");
        Check(weapon.bones==1&&weapon.packets.size()==1&&weapon.vertices.size()==243&&weapon.time.size()==60,"unexpected weapon source contract");
        Check(twisted.bones==11&&twisted.packets.size()==28&&twisted.vertices.size()==1800&&twisted.time.size()==60,"unexpected Twisted source contract");
        const auto a=CheckSkin(aya),w=CheckSkin(weapon),t=CheckSkin(twisted);
        const auto pc=T3BSource::ToPC(aya, T3BSource::PoseOriginal(aya,aya.time.front()).front(), scene.player[0], scene.player[1], scene.player[2]);
        Check(std::isfinite(pc.x)&&std::isfinite(pc.y)&&std::isfinite(pc.z),"source to PC transform failed");
        std::ofstream out(argv[5],std::ios::binary); Check(static_cast<bool>(out),"source probe output open failed");
        out<<"{\n  \"schema\": \"t3b-ue-source-bundle-probe/v1\",\n  \"status\": \"passed\",\n";
        out<<"  \"scene\": {\"draws\": "<<scene.draws.size()<<", \"vertices\": "<<scene.vertices.size()<<", \"materials\": "<<scene.materials<<"},\n";
        out<<"  \"actors\": {\"Aya\": {\"bones\": "<<aya.bones<<", \"packets\": "<<aya.packets.size()<<", \"vertices\": "<<aya.vertices.size()<<", \"frames\": "<<a.poses<<", \"posed_points\": "<<a.points<<"},\n";
        out<<"             \"Weapon\": {\"bones\": "<<weapon.bones<<", \"packets\": "<<weapon.packets.size()<<", \"vertices\": "<<weapon.vertices.size()<<", \"frames\": "<<w.poses<<", \"posed_points\": "<<w.points<<"},\n";
        out<<"             \"Twisted\": {\"bones\": "<<twisted.bones<<", \"packets\": "<<twisted.packets.size()<<", \"vertices\": "<<twisted.vertices.size()<<", \"frames\": "<<t.poses<<", \"posed_points\": "<<t.points<<"}},\n";
        out<<"  \"coordinates\": {\"player_spawn_x\": "<<std::setprecision(9)<<scene.player[0]<<", \"player_spawn_z\": "<<scene.player[1]<<", \"player_yaw\": "<<scene.player[2]<<", \"first_aya_pc\": ["<<pc.x<<", "<<pc.y<<", "<<pc.z<<"]},\n";
        out<<"  \"raw_affine_policy\": \"PoseOriginal interpolates all 12 affine components; no FTransform decomposition\"\n}\n";
        return 0;
    } catch(const std::exception& e){std::ofstream("source_bundle_probe_error.txt")<<e.what()<<'\n';return 1;}
}
