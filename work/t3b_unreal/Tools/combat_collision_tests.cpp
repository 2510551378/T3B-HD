#include "../Source/T3BRemake/Private/T3BCombatCollision.h"

#include <cmath>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>

namespace {
using namespace T3BCombat;
unsigned checks{},failures{};
void Check(bool passed,const std::string& name) { checks++;if(!passed){failures++;std::cerr<<"FAIL "<<name<<'\n';} }
bool Near(float a,float b,float tolerance=1e-4f) { return std::abs(a-b)<tolerance; }
void Reject(const std::function<void()>& run,const std::string& name) {
    bool rejected=false;try{run();}catch(const T3BSource::FormatError&){rejected=true;}Check(rejected,name);
}
void Triangle(T3BSource::Scene& scene,Vec3 a,Vec3 b,Vec3 c,std::uint32_t material=0,std::uint8_t alpha=255) {
    const auto first=static_cast<std::uint32_t>(scene.vertices.size());
    for(const auto p:{a,b,c})scene.vertices.push_back({p,{0,0},{255,255,255,alpha}});
    scene.draws.push_back({first,3,material});
}
void Floor(T3BSource::Scene& scene,float x0,float x1,float z0,float z1,float y=0) {
    Triangle(scene,{x0,y,z0},{x0,y,z1},{x1,y,z1});Triangle(scene,{x0,y,z0},{x1,y,z1},{x1,y,z0});
}
void Wall(T3BSource::Scene& scene,float x,float y0=0,float y1=3,float z0=-5,float z1=5) {
    Triangle(scene,{x,y0,z0},{x,y1,z0},{x,y1,z1});Triangle(scene,{x,y0,z0},{x,y1,z1},{x,y0,z1});
}
T3BSource::Scene Base() { T3BSource::Scene scene;scene.materials=1;Floor(scene,-10,10,-10,10);return scene; }
CollisionWorld World(const T3BSource::Scene& scene) { CollisionWorld world;world.Build(scene,std::vector<bool>(scene.materials,true));return world; }
} // namespace

int main(int argc,char** argv) {
    auto scene=Base();Wall(scene,1);Wall(scene,3);auto world=World(scene);
    Check(world.SolidTriangleCount()==6&&world.FloorTriangleCount()==2,"visible triangles and walkable floors counted");
    const auto nearest=world.Raycast({-1,1,0},{5,1,0});
    Check(nearest.hit&&Near(nearest.distance,2)&&Near(nearest.position.x,1)&&nearest.material==0,"nearest double-sided triangle ray hit");
    Check(Near(nearest.normal.x,-1)&&Near(nearest.normal.y,0),"ray normal opposes incoming direction");
    const auto reverse=world.Raycast({2,1,0},{-1,1,0});
    Check(reverse.hit&&Near(reverse.distance,1)&&Near(reverse.normal.x,1),"backface ray hit normal flipped");
    Check(!world.Raycast({-1,4,0},{5,4,0}).hit,"ray above geometry misses");
    Check(world.Raycast({-1,1,0},{1,1,0}).hit,"closed segment endpoint hits");
    Check(!world.Raycast({-1,1,0},{.99f,1,0}).hit,"ray does not enlarge target");
    const auto down=world.Raycast({0,1,0},{0,-1,0});
    Check(down.hit&&Near(down.distance,1)&&Near(down.normal.y,1),"downward ground ray");
    float ground=123;
    Check(world.FindGround({0,.1f,0},.1f,.2f,ground)&&Near(ground,0),"find floor below feet");
    Check(!world.FindGround({0,1,0},0,.5f,ground)&&Near(ground,0),"limited drop leaves output unchanged on miss");
    const auto walk=world.MoveCapsule({-2,.01f,0},{1,0,0});
    Check(Near(walk.position.x,-1)&&Near(walk.position.y,0)&&walk.grounded&&!walk.wallBlocked,"grounded free movement snaps feet");
    const auto blocked=world.MoveCapsule({0,0,0},{4,0,0});
    Check(blocked.wallBlocked&&blocked.position.x<=.721f&&blocked.position.x>.59f&&blocked.grounded,"bounded substeps stop capsule before thin wall");
    const auto slide=world.MoveCapsule({0,0,0},{2,0,2});
    Check(slide.wallBlocked&&slide.position.x<=.721f&&slide.position.z>1.9f,"wall collision allows tangential axis sliding");
    const auto floorWorld=World(Base());
    const auto edge=floorWorld.MoveCapsule({9,0,0},{3,0,0});
    Check(edge.floorBlocked&&edge.position.x<=9.721f&&edge.position.x>9.5f,"nine support samples prevent walking off edge");
    const auto stationary=floorWorld.MoveCapsule({0,.03f,0},{0,0,0});
    Check(stationary.grounded&&Near(stationary.position.y,0),"zero movement grounds capsule");
    auto stepScene=Base();Floor(stepScene,0,4,-4,4,.2f);Wall(stepScene,0,0,.2f,-4,4);const auto stepWorld=World(stepScene);
    const auto step=stepWorld.MoveCapsule({-1,0,0},{2,0,0});
    Check(step.grounded&&step.stepped&&Near(step.position.x,1)&&Near(step.position.y,.2f),"adapter climbs step within allowed rise");
    const auto descend=stepWorld.MoveCapsule({1,.2f,0},{-2,0,0});
    Check(descend.grounded&&Near(descend.position.x,-1)&&Near(descend.position.y,0),"adapter descends small step");
    const auto noStep=stepWorld.MoveCapsule({-1,0,0},{2,0,0},.28f,1.84f,0);
    Check(noStep.wallBlocked&&noStep.position.x<0&&!noStep.stepped,"zero step allowance does not climb riser");
    auto highScene=Base();Floor(highScene,0,4,-4,4,.8f);Wall(highScene,0,0,.8f,-4,4);const auto tall=World(highScene).MoveCapsule({-1,0,0},{2,0,0});
    Check(tall.wallBlocked&&tall.position.x<0&&!tall.stepped,"tall step remains blocking");
    auto ceilingScene=Base();Triangle(ceilingScene,{-3,1.7f,-3},{3,1.7f,-3},{3,1.7f,3});Triangle(ceilingScene,{-3,1.7f,-3},{3,1.7f,3},{-3,1.7f,3});
    const auto ceiling=World(ceilingScene).MoveCapsule({-4,0,0},{4,0,0});
    Check(ceiling.wallBlocked&&ceiling.position.x< -3,"downward ceiling blocks capsule body");
    auto overheadScene=Base();Floor(overheadScene,-3,3,-3,3,1.7f);
    Check(World(overheadScene).MoveCapsule({-4,0,0},{4,0,0}).wallBlocked,"upward overhead platform also blocks capsule body");
    auto transparent=Base();transparent.materials=2;Triangle(transparent,{0,0,0},{0,1,0},{0,1,1},1);Triangle(transparent,{2,0,0},{2,1,0},{2,1,1},0,0);
    CollisionWorld filtered;filtered.Build(transparent,{true,false});
    Check(filtered.SolidTriangleCount()==2&&filtered.ExcludedVertexAlphaCount()==1,"material proof and vertex alpha zero exclude surfaces");
    Check(!filtered.Raycast({-1,.5f,.5f},{3,.5f,.5f}).hit,"excluded transparent triangles never block ray");
    auto degenerate=Base();Triangle(degenerate,{0,1,0},{0,1,0},{0,1,0});const auto degenerateWorld=World(degenerate);
    Check(degenerateWorld.SolidTriangleCount()==3&&!degenerateWorld.Raycast({-1,1,0},{1,1,0}).hit,"degenerate source triangle counted but never a ray target");
    CollisionWorld empty;Check(!empty.Raycast({0,1,0},{0,-1,0}).hit,"unbuilt world has no hit");
    Check(!empty.MoveCapsule({0,0,0},{1,0,0}).grounded,"unbuilt world refuses unsupported movement");
    const auto baseline=world.SolidTriangleCount();
    Reject([&]{world.Build(scene,{});},"reject material proof mismatch");
    auto invalid=scene;invalid.draws[0].first=1;Reject([&]{world.Build(invalid,{true});},"reject discontinuous draw coverage");
    invalid=scene;invalid.vertices[0].position.x=NAN;Reject([&]{world.Build(invalid,{true});},"reject nonfinite geometry");
    invalid=scene;invalid.draws[0].material=1;Reject([&]{world.Build(invalid,{true});},"reject material index out of range");
    invalid=scene;invalid.draws[0].count=std::numeric_limits<std::uint32_t>::max();Reject([&]{world.Build(invalid,{true});},"reject overflowing draw range");
    Check(world.SolidTriangleCount()==baseline,"invalid build preserves prior collision world");
    Reject([&]{world.Raycast({0,0,0},{0,0,0});},"reject zero length ray");
    Reject([&]{world.Raycast({NAN,0,0},{1,0,0});},"reject nonfinite ray");
    Reject([&]{world.FindGround({0,0,0},-1,0,ground);},"reject negative ground rise");
    Reject([&]{world.FindGround({0,NAN,0},0,0,ground);},"reject nonfinite ground position");
    Reject([&]{world.MoveCapsule({0,0,0},{1,0,0},0);},"reject zero radius");
    Reject([&]{world.MoveCapsule({0,0,0},{1,0,0},1,1);},"reject capsule height less than diameter");
    Reject([&]{world.MoveCapsule({0,0,0},{NAN,0,0});},"reject nonfinite movement");
    Reject([&]{world.MoveCapsule({0,0,0},{1,0,0},.28f,1.84f,-1);},"reject negative step policy");
    Reject([&]{world.MoveCapsule({0,0,0},{10000,0,0});},"reject movement exceeding bounded substep count");

    // Optional original-asset check. Flags are supplied by an external texture
    // alpha audit, keeping this core and its default tests asset-independent.
    if(argc==3) {
        std::ifstream binary(argv[1],std::ios::binary),flagsFile(argv[2]);
        if(!binary||!flagsFile){std::cerr<<"asset inputs unavailable\n";return 2;}
        const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(binary),{}};
        const auto source=T3BSource::LoadScene(bytes);std::vector<bool> flags;int flag;
        while(flagsFile>>flag){if(flag!=0&&flag!=1){std::cerr<<"invalid material flag\n";return 2;}flags.push_back(flag!=0);}
        auto real=CollisionWorld{};real.Build(source,flags);
        Check(real.SolidTriangleCount()==8551,"original alpha-proven solid triangle count matches C adapter");
        float y;
        Check(real.FindGround({source.player[0],0,source.player[1]},.3f,.3f,y),"original player spawn has walkable support");
        const auto standing=real.MoveCapsule({source.player[0],0,source.player[1]},{0,0,0});
        Check(standing.grounded&&!standing.wallBlocked&&!standing.floorBlocked,"original source spawn capsule is clear and supported");
        std::cout<<"source_solid_triangles="<<real.SolidTriangleCount()<<"\nsource_walkable_triangles="<<real.FloorTriangleCount()<<"\nsource_spawn="<<source.player[0]<<','<<y<<','<<source.player[1]<<'\n';
    }
    std::cout<<"combat_collision_checks="<<checks<<"\ncombat_collision_failures="<<failures<<'\n';return failures?1:0;
}
