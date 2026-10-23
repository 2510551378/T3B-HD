#include "T3BSourceData.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

#if defined(_MSC_VER)
#pragma float_control(precise, on, push)
#pragma fp_contract(off)
#elif defined(__clang__)
#pragma clang fp contract(off)
#pragma clang fp reassociate(off)
#endif

namespace T3BSource {
namespace {
class Reader {
public:
    explicit Reader(const std::vector<std::uint8_t>& bytes) : data(bytes) {}
    void Magic(const char* magic) {
        Need(8);if(std::memcmp(data.data()+offset,magic,8))throw FormatError("invalid source magic");offset+=8;
    }
    std::uint32_t U32() {
        Need(4);const auto* p=data.data()+offset;offset+=4;
        return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);
    }
    std::int32_t I32() { const std::uint32_t bits=U32();std::int32_t result;std::memcpy(&result,&bits,4);return result; }
    float F32() {
        const std::uint32_t bits=U32();float result;std::memcpy(&result,&bits,4);
        if(!std::isfinite(result))throw FormatError("non-finite source float");
        return result;
    }
    std::uint8_t U8() { Need(1);return data[offset++]; }
    void ExactSize(std::uint64_t expected) const { if(expected!=data.size())throw FormatError("source byte count mismatch"); }
    void End() const { if(offset!=data.size())throw FormatError("unconsumed source bytes"); }
private:
    void Need(std::size_t count) const { if(offset>data.size()||count>data.size()-offset)throw FormatError("truncated source data"); }
    const std::vector<std::uint8_t>& data;std::size_t offset{};
};
void Range(std::uint32_t value,std::uint32_t minimum,std::uint32_t maximum,const char* message) {
    if(value<minimum||value>maximum)throw FormatError(message);
}
Vec3 ReadVec3(Reader& reader) { return {reader.F32(),reader.F32(),reader.F32()}; }
Vec2 ReadVec2(Reader& reader) { return {reader.F32(),reader.F32()}; }
void Finite(Vec3 point) {
    if(!std::isfinite(point.x)||!std::isfinite(point.y)||!std::isfinite(point.z))throw FormatError("non-finite transformed source point");
}
void ValidateParents(const Skin& skin) {
    for(std::uint32_t index=0;index<skin.bones;index++) {
        std::int32_t parent=skin.parent[index];
        if(parent< -1||parent>=static_cast<std::int32_t>(skin.bones))throw FormatError("source parent index out of range");
    }
    for(std::uint32_t index=0;index<skin.bones;index++) {
        std::int32_t current=static_cast<std::int32_t>(index);std::uint32_t depth=0;
        while(current>=0) { if(depth++>=skin.bones)throw FormatError("source parent cycle");current=skin.parent[static_cast<std::size_t>(current)]; }
    }
}
} // namespace

Scene LoadScene(const std::vector<std::uint8_t>& bytes) {
    Reader reader(bytes);reader.Magic("T3BSCN1\0");if(reader.U32()!=1)throw FormatError("unsupported scene version");
    const std::uint32_t draws=reader.U32(),vertices=reader.U32(),materials=reader.U32();
    Range(draws,1,4096,"invalid scene draw count");Range(vertices,1,10000000,"invalid scene vertex count");Range(materials,1,4096,"invalid scene material count");
    reader.ExactSize(56+std::uint64_t(draws)*12+std::uint64_t(vertices)*24);
    Scene scene;scene.materials=materials;
    for(float& value:scene.player)value=reader.F32();
    for(float& value:scene.enemy)value=reader.F32();
    scene.units=reader.F32();scene.floor=reader.F32();
    if(scene.units<=0)throw FormatError("invalid scene units");
    scene.draws.resize(draws);scene.vertices.resize(vertices);std::uint32_t next=0;
    for(auto& draw:scene.draws) {
        draw={reader.U32(),reader.U32(),reader.U32()};
        if(draw.first!=next||draw.count==0||draw.count%3||draw.count>vertices-next||draw.material>=materials)throw FormatError("invalid scene draw coverage/material");
        next+=draw.count;
    }
    if(next!=vertices)throw FormatError("incomplete scene vertex coverage");
    for(auto& vertex:scene.vertices) { vertex.position=ReadVec3(reader);vertex.uv=ReadVec2(reader);for(auto& value:vertex.rgba)value=reader.U8(); }
    reader.End();return scene;
}

Skin LoadSkin(const std::vector<std::uint8_t>& bytes) {
    Reader reader(bytes);reader.Magic("T3BSKN2\0");if(reader.U32()!=2)throw FormatError("unsupported skin version");
    Skin skin;skin.bones=reader.U32();const std::uint32_t packets=reader.U32(),vertices=reader.U32(),frames=reader.U32();skin.materials=reader.U32();skin.flags=reader.U32();
    const std::uint32_t reserved=reader.U32();const float reserved0=reader.F32();skin.units=reader.F32();skin.floor=reader.F32();const float reserved1=reader.F32();
    Range(skin.bones,1,64,"invalid source bone count");Range(packets,1,4096,"invalid skin packet count");Range(vertices,1,100000,"invalid skin vertex count");Range(frames,2,4096,"invalid skin sample count");Range(skin.materials,1,16,"invalid skin material count");
    if(skin.units<=0||reserved||reserved0!=0||reserved1!=0)throw FormatError("invalid skin units/reserved header");
    reader.ExactSize(56+std::uint64_t(skin.bones)*4+std::uint64_t(packets)*16+std::uint64_t(vertices)*100+std::uint64_t(frames)*4+std::uint64_t(frames)*skin.bones*48);
    skin.parent.resize(skin.bones);for(auto& value:skin.parent)value=reader.I32();ValidateParents(skin);
    skin.packets.resize(packets);std::uint32_t next=0;
    for(auto& packet:skin.packets) {
        packet={reader.U32(),reader.U32(),reader.U32(),reader.U32()};
        if(packet.first!=next||packet.count==0||packet.count%3||packet.count>vertices-next||packet.material>=skin.materials||packet.primitive!=3)throw FormatError("invalid skin packet coverage/material/primitive");
        next+=packet.count;
    }
    if(next!=vertices)throw FormatError("incomplete skin vertex coverage");
    skin.vertices.resize(vertices);
    for(auto& vertex:skin.vertices) {
        vertex.position=ReadVec3(reader);vertex.uv=ReadVec2(reader);vertex.normal=ReadVec3(reader);vertex.count=reader.U32();Range(vertex.count,1,8,"invalid influence count");
        for(auto& bone:vertex.bone){bone=reader.U32();if(bone>=skin.bones)throw FormatError("source influence index out of range");}
        float sum=0;
        for(std::uint32_t influence=0;influence<8;influence++) {
            float& weight=vertex.weight[influence];weight=reader.F32();
            if(weight<0||(influence>=vertex.count&&weight!=0))throw FormatError("invalid source influence weight");
            if(influence<vertex.count)sum+=weight;
        }
        if(sum<.95f||sum>1.01f)throw FormatError("invalid source influence weight sum");
    }
    skin.time.resize(frames);for(std::uint32_t sample=0;sample<frames;sample++) {
        skin.time[sample]=reader.F32();if((sample==0&&skin.time[sample]!=0)||(sample&&skin.time[sample]<=skin.time[sample-1]))throw FormatError("invalid source sample times");
    }
    skin.matrix.resize(std::size_t(frames)*skin.bones*12);for(float& component:skin.matrix)component=reader.F32();
    reader.End();return skin;
}

std::vector<Vec3> PoseOriginal(const Skin& skin,float seconds) {
    if(!std::isfinite(seconds))throw FormatError("non-finite source pose time");
    if(skin.bones==0||skin.bones>64||skin.time.size()<2||skin.matrix.size()!=skin.time.size()*skin.bones*12)throw FormatError("invalid pose storage shape");
    const float time=std::max(0.0f,std::min(seconds,skin.time.back()));
    std::size_t a=0;while(a+1<skin.time.size()&&skin.time[a+1]<=time)a++;
    const std::size_t b=a+1<skin.time.size()?a+1:a;const float mix=a==b?0:(time-skin.time[a])/(skin.time[b]-skin.time[a]);
    float matrix[64][12];
    for(std::uint32_t bone=0;bone<skin.bones;bone++)for(std::uint32_t component=0;component<12;component++)matrix[bone][component]=skin.matrix[(a*skin.bones+bone)*12+component]*(1-mix)+skin.matrix[(b*skin.bones+bone)*12+component]*mix;
    std::vector<Vec3> posed(skin.vertices.size());
    for(std::size_t index=0;index<skin.vertices.size();index++) {
        const auto& vertex=skin.vertices[index];if(vertex.count==0||vertex.count>8)throw FormatError("invalid posed influence count");Vec3 point{};
        for(std::uint32_t influence=0;influence<vertex.count;influence++) {
            if(vertex.bone[influence]>=skin.bones)throw FormatError("invalid posed source index");
            const float* m=matrix[vertex.bone[influence]];const float weight=vertex.weight[influence];
            point.x+=weight*(m[0]*vertex.position.x+m[1]*vertex.position.y+m[2]*vertex.position.z+m[3]);
            point.y+=weight*(m[4]*vertex.position.x+m[5]*vertex.position.y+m[6]*vertex.position.z+m[7]);
            point.z+=weight*(m[8]*vertex.position.x+m[9]*vertex.position.y+m[10]*vertex.position.z+m[11]);
        }
        Finite(point);posed[index]=point;
    }
    return posed;
}

Vec3 ToPC(const Skin& skin,Vec3 point,float actorX,float actorZ,float yaw) {
    Finite(point);if(!std::isfinite(skin.units)||skin.units<=0||!std::isfinite(skin.floor)||!std::isfinite(actorX)||!std::isfinite(actorZ)||!std::isfinite(yaw))throw FormatError("invalid PC transform");
    point.x*=skin.units;point.y=(point.y-skin.floor)*skin.units;point.z*=skin.units;const float sn=std::sin(yaw),cs=std::cos(yaw);
    Vec3 result={actorX+point.x*cs+point.z*sn,point.y,actorZ-point.x*sn+point.z*cs};Finite(result);return result;
}
Vec3 ToUE(Vec3 pc) { Finite(pc);Vec3 result={pc.z*100,-pc.x*100,pc.y*100};Finite(result);return result; }
} // namespace T3BSource

#if defined(_MSC_VER)
#pragma float_control(pop)
#endif
