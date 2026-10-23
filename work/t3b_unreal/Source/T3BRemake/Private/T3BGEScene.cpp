#include "T3BGEScene.h"
#include "T3BGEEffectGeometry.h"
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace {
void Check(bool v,const char* s){if(!v)throw std::runtime_error(s);}
class Reader {
    const std::vector<std::uint8_t>& bytes;std::size_t at=0;
public:
    explicit Reader(const std::vector<std::uint8_t>& b):bytes(b){Check(b.size()<=256u*1024u*1024u,"Scene input too large");}
    void Need(std::size_t n)const{Check(n<=bytes.size()-at,"Scene input truncated");}
    std::uint32_t Word(){Need(4);const auto* p=bytes.data()+at;at+=4;return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
    float Float(){auto w=Word();float v;std::memcpy(&v,&w,4);Check(std::isfinite(v),"Scene nonfinite float");return v;}
    std::vector<std::uint8_t> Bytes(std::size_t n){Need(n);auto result=std::vector<std::uint8_t>(bytes.begin()+at,bytes.begin()+at+n);at+=n;return result;}
    void Magic(const char* expected){const auto actual=Bytes(8);Check(!std::memcmp(actual.data(),expected,8),"Scene transport magic differs");}
    bool End()const{return at==bytes.size();}
};
T3BGE::GPUAtlas Atlas(Reader& r){
    T3BGE::GPUAtlas t;t.width=r.Word();t.height=r.Word();Check(t.width>0&&t.height>0&&t.width<=4096&&t.height<=4096,"Scene atlas dimensions");
    t.rgba=r.Bytes(std::size_t(t.width)*t.height*4);return t;
}
void Parameters(Reader& r,T3BGE::SceneDraw& d){
    for(auto& x:d.localToClip){x=r.Float();}
    for(auto& x:d.fog){x=r.Float();}
    for(auto& x:d.fogRGB){x=r.Word();Check(x<=255,"Scene fog color outside byte range");}
}
void Vertices(Reader& r,T3BGE::SceneDraw& d,std::uint32_t n){
    Check(n>0&&n<=65535&&n%3==0,"Scene triangle extent");r.Need(std::size_t(n)*36);d.vertices.resize(n);
    for(auto& v:d.vertices){for(auto& x:v.position)x=r.Float();for(auto& x:v.uv)x=r.Float();for(auto& x:v.color){x=r.Float();Check(x>=0&&x<=1,"Scene color outside UNORM");}}
}
void State(const T3BGE::SceneDraw& d,std::size_t atlases){
    Check(d.texture<atlases&&d.flags<32768&&(d.flags&128)==0&&d.stencilRef<=255,"Unsupported scene draw state");
    Check(!(d.flags&32)||d.stencilRef==0,"Unsupported scene stencil reference");
    Check(!(d.flags&2048)||(d.flags&1025)==1025,"Invalid additive scene flags");
    Check(!(d.flags&1024)||(d.flags&1),"Premultiplied source requires blending");
}
bool SameVertices(const std::vector<T3BGE::GPUVertex>& a,const std::vector<T3BGE::GPUVertex>& b){return a.size()==b.size()&&!std::memcmp(a.data(),b.data(),a.size()*sizeof(T3BGE::GPUVertex));}
std::vector<T3BGE::GPUVertex> Expand(const T3BGE::EffectGeometry& mesh){
    std::vector<T3BGE::GPUVertex> result;result.reserve(mesh.triangleIndices.size());
    for(auto i:mesh.triangleIndices){const auto& s=mesh.vertices[i];T3BGE::GPUVertex v{};
        for(unsigned k=0;k<3;++k){v.position[k]=s.position[k];}
        for(unsigned k=0;k<2;++k){v.uv[k]=s.uv[k];}
        for(unsigned k=0;k<4;++k){v.color[k]=static_cast<float>(s.color[k])/255.f;}
        result.push_back(v);
    }return result;
}
}
namespace T3BGE {
SceneGeometry LoadSceneGeometry(const std::vector<std::uint8_t>& bytes){
    Reader r(bytes);r.Magic("T3BSFC1\0");SceneGeometry scene;scene.width=r.Word();scene.height=r.Word();const auto frames=r.Word(),atlases=r.Word();
    Check(scene.width==480&&scene.height==272&&frames>0&&frames<=4096&&atlases>0&&atlases<=256,"Unsupported source scene scope");
    for(std::uint32_t i=0;i<atlases;++i)scene.atlases.push_back(Atlas(r));
    for(std::uint32_t i=0;i<frames;++i){
        SceneFrame f;f.sample=r.Word();const auto n=r.Word();Check(f.sample==i&&n>0&&n<=4096,"Scene frame order/bounds");
        for(std::uint32_t j=0;j<n;++j){
            SceneDraw d;d.texture=r.Word();d.ordinal=r.Word();d.flags=r.Word();const auto nv=r.Word();d.stencilRef=r.Word();
            State(d,atlases);Check(d.ordinal==j,"Scene draw order");Parameters(r,d);Vertices(r,d,nv);f.draws.push_back(std::move(d));
        }scene.frames.push_back(std::move(f));
    }Check(r.End(),"Scene trailing bytes");return scene;
}
SceneEffectBindings LoadSceneEffectBindings(const std::vector<std::uint8_t>& bytes){
    Reader r(bytes);r.Magic("T3BPCG1\0");const auto w=r.Word(),h=r.Word(),frames=r.Word(),atlases=r.Word();
    Check(w==480&&h==272&&frames>0&&frames<=4096&&atlases>0&&atlases<=256,"Effect binding scope");SceneEffectBindings result;
    for(std::uint32_t i=0;i<atlases;++i)result.atlases.push_back(Atlas(r));
    for(std::uint32_t i=0;i<frames;++i){
        Check(r.Word()==i,"Effect frame order");const auto n=r.Word();Check(n>0&&n<=4096,"Effect draw bounds");std::vector<SceneEffectBinding> frame;
        for(std::uint32_t j=0;j<n;++j){
            SceneEffectBinding b;auto& d=b.expected;d.ordinal=j;d.texture=r.Word();d.flags=r.Word();d.stencilRef=r.Word();State(d,atlases);Parameters(r,d);
            Check((d.flags&4096)&&!(d.flags&34),"Effect binding must not write depth/stencil");
            for(auto& x:b.registers){x=r.Word();Check(x<=0xffffff,"Effect register outside F24 payload");}
            b.vtype=r.Word();b.count=r.Word();b.mode=r.Word();const auto size=r.Word();
            Check(b.vtype==0x11e&&b.count>=3&&b.count<=4096&&b.mode<=255&&size>0&&size<=16384&&size%4==0,"Effect operand contract");
            for(auto& x:b.source){x=r.Float();}
            for(auto& x:b.parent){x=r.Float();}
            b.palette=r.Bytes(size);
            for(std::uint32_t k=0;k<b.count;++k){const auto index=r.Word();Check(index<size/4,"Effect color reference outside palette");b.colorIndices.push_back(index);}
            b.before=r.Bytes(b.count*16);b.expectedAfter=r.Bytes(b.count*16);Vertices(r,d,r.Word());frame.push_back(std::move(b));
        }result.frames.push_back(std::move(frame));
    }Check(r.End(),"Effect binding trailing bytes");return result;
}
SceneFrame EvaluateSceneFrame(const SceneGeometry& scene,std::uint32_t sample,const SceneEffectBindings* effects){
    Check(sample<scene.frames.size(),"Scene sample outside capture");SceneFrame result=scene.frames[sample];
    if(!effects)return result;
    Check(effects->frames.size()==scene.frames.size(),"Effect and scene samples differ");const auto& bindings=effects->frames[sample];std::size_t k=0;
    for(auto& d:result.draws){
        if(!(d.flags&4096))continue;
        Check(k<bindings.size(),"Missing source color binding");const auto& b=bindings[k++];const auto& e=b.expected;
        Check(d.flags==e.flags&&d.stencilRef==e.stencilRef&&d.localToClip==e.localToClip&&d.fog==e.fog&&d.fogRGB==e.fogRGB&&SameVertices(d.vertices,e.vertices),"Effect binding does not match source scene draw");
        const auto& t=scene.atlases.at(d.texture);const auto& et=effects->atlases.at(e.texture);
        Check(t.width==et.width&&t.height==et.height&&t.rgba==et.rgba,"Effect CLUT texture binding differs");
        const auto tint=ProcessOriginalEffectColorMode(ModulateOriginalEffectRGBA(b.source,b.parent),static_cast<std::uint8_t>(b.mode));
        const auto palette=ModulateOriginalEffectVertexPalette(b.palette,tint);auto raw=b.before;PatchOriginalEffectVertexColors(b.vtype,raw,b.colorIndices,palette);
        Check(raw==b.expectedAfter,"Effect palette/patch differs from original GE bytes");
        auto vertices=Expand(DecodeOriginalEffectStrip(b.vtype,b.count,raw,b.registers));Check(SameVertices(vertices,e.vertices),"Effect geometry differs from source GE");d.vertices=std::move(vertices);
    }Check(k==bindings.size(),"Unconsumed source color binding");return result;
}
} // namespace T3BGE
