#include "T3BCombatCollision.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace T3BCombat {
namespace {
struct D3 { double x{}, y{}, z{}; };
D3 D(Vec3 p) { return {p.x,p.y,p.z}; }
D3 Sub(D3 a,D3 b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
D3 Add(D3 a,D3 b,double scale) { return {a.x+b.x*scale,a.y+b.y*scale,a.z+b.z*scale}; }
double Dot(D3 a,D3 b) { return a.x*b.x+a.y*b.y+a.z*b.z; }
D3 Cross(D3 a,D3 b) { return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x}; }
double Clamp(double value) { return std::max(0.0,std::min(1.0,value)); }
bool Finite(Vec3 p) { return std::isfinite(p.x)&&std::isfinite(p.y)&&std::isfinite(p.z); }
void Require(bool valid,const char* message) { if(!valid)throw T3BSource::FormatError(message); }

// Double-sided Moller-Trumbore and segment/triangle distance adapted from the
// C prototype's combat_triangle.h/combat_capsule_triangle.h. All intermediate
// geometry uses double, retaining the source mesh without enlarged hit boxes.
bool RayTriangle(Vec3 origin,D3 direction,double maxDistance,Vec3 a,Vec3 b,Vec3 c,double& distance) {
    const D3 e1=Sub(D(b),D(a)),e2=Sub(D(c),D(a));
    const D3 p=Cross(direction,e2);const double determinant=Dot(e1,p);
    const double scale=std::sqrt(Dot(e1,e1)*Dot(e2,e2));
    if(scale==0||std::abs(determinant)<=16*std::numeric_limits<double>::epsilon()*scale)return false;
    const D3 t=Sub(D(origin),D(a));const double inverse=1/determinant;
    const double u=Dot(t,p)*inverse;
    if(u<0||u>1)return false;
    const D3 q=Cross(t,e1);const double v=Dot(direction,q)*inverse;
    if(v<0||u+v>1)return false;
    const double hit=Dot(e2,q)*inverse;
    if(hit<0||hit>maxDistance)return false;
    distance=hit;return true;
}
double PointSegment(D3 p,D3 a,D3 b) {
    const D3 ab=Sub(b,a);const double length=Dot(ab,ab);
    const D3 delta=Sub(p,Add(a,ab,length>0?Clamp(Dot(Sub(p,a),ab)/length):0));return Dot(delta,delta);
}
double SegmentSegment(D3 p1,D3 q1,D3 p2,D3 q2) {
    const D3 d1=Sub(q1,p1),d2=Sub(q2,p2),r=Sub(p1,p2);
    const double a=Dot(d1,d1),e=Dot(d2,d2),f=Dot(d2,r);double s=0,t=0;
    if(a==0&&e==0)return Dot(r,r);
    if(a==0)t=Clamp(f/e);
    else {
        const double c=Dot(d1,r);
        if(e==0)s=Clamp(-c/a);
        else {
            const double b=Dot(d1,d2),denominator=a*e-b*b;
            if(denominator>0)s=Clamp((b*f-c*e)/denominator);
            t=(b*s+f)/e;
            if(t<0){t=0;s=Clamp(-c/a);}else if(t>1){t=1;s=Clamp((b-c)/a);}
        }
    }
    const D3 delta=Sub(Add(p1,d1,s),Add(p2,d2,t));return Dot(delta,delta);
}
double PointTriangle(D3 p,D3 a,D3 b,D3 c) {
    const D3 ab=Sub(b,a),ac=Sub(c,a),ap=Sub(p,a),normal=Cross(ab,ac);
    if(Dot(normal,normal)==0)return std::min(PointSegment(p,a,b),std::min(PointSegment(p,b,c),PointSegment(p,c,a)));
    const double d1=Dot(ab,ap),d2=Dot(ac,ap);if(d1<=0&&d2<=0)return Dot(ap,ap);
    const D3 bp=Sub(p,b);const double d3=Dot(ab,bp),d4=Dot(ac,bp);if(d3>=0&&d4<=d3)return Dot(bp,bp);
    const double vc=d1*d4-d3*d2;
    if(vc<=0&&d1>=0&&d3<=0){const D3 delta=Sub(p,Add(a,ab,d1/(d1-d3)));return Dot(delta,delta);}
    const D3 cp=Sub(p,c);const double d5=Dot(ab,cp),d6=Dot(ac,cp);if(d6>=0&&d5<=d6)return Dot(cp,cp);
    const double vb=d5*d2-d1*d6;
    if(vb<=0&&d2>=0&&d6<=0){const D3 delta=Sub(p,Add(a,ac,d2/(d2-d6)));return Dot(delta,delta);}
    const double va=d3*d6-d5*d4;
    if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0){const D3 delta=Sub(p,Add(b,Sub(c,b),(d4-d3)/((d4-d3)+(d5-d6))));return Dot(delta,delta);}
    const double inverse=1/(va+vb+vc);const D3 delta=Sub(p,Add(Add(a,ab,vb*inverse),ac,vc*inverse));return Dot(delta,delta);
}
double CapsuleDistance(Vec3 feet,float radius,float height,Vec3 a,Vec3 b,Vec3 c) {
    const Vec3 lower{feet.x,feet.y+radius,feet.z},upper{feet.x,feet.y+height-radius,feet.z};
    const double length=static_cast<double>(height)-2*radius;double hit;
    if(length>0&&RayTriangle(lower,{0,1,0},length,a,b,c,hit))return 0;
    const D3 p=D(lower),q=D(upper),da=D(a),db=D(b),dc=D(c);
    return std::min({PointTriangle(p,da,db,dc),PointTriangle(q,da,db,dc),
                     SegmentSegment(p,q,da,db),SegmentSegment(p,q,db,dc),SegmentSegment(p,q,dc,da)});
}
} // namespace

void CollisionWorld::Build(const T3BSource::Scene& scene,const std::vector<bool>& materialSolid) {
    Require(scene.materials>0&&materialSolid.size()==scene.materials,"collision material flag count mismatch");
    Require(!scene.vertices.empty()&&!scene.draws.empty(),"collision scene is empty");
    std::vector<Triangle> triangles;std::vector<std::uint32_t> floors;std::size_t excluded=0,expected=0;
    triangles.reserve(scene.vertices.size()/3);
    for(const auto& draw:scene.draws) {
        Require(draw.material<scene.materials&&draw.first==expected&&draw.count>0&&draw.count%3==0&&
                draw.first<=scene.vertices.size()&&draw.count<=scene.vertices.size()-draw.first,"collision invalid scene draw");
        expected+=draw.count;
        for(std::size_t vertex=draw.first;vertex<expected;vertex+=3) {
            const auto& va=scene.vertices[vertex];const auto& vb=scene.vertices[vertex+1];const auto& vc=scene.vertices[vertex+2];
            Require(Finite(va.position)&&Finite(vb.position)&&Finite(vc.position),"collision nonfinite scene vertex");
            if(!materialSolid[draw.material])continue;
            if(!va.rgba[3]||!vb.rgba[3]||!vc.rgba[3]){excluded++;continue;}
            Triangle t;t.a=va.position;t.b=vb.position;t.c=vc.position;t.source=static_cast<std::uint32_t>(vertex/3);t.material=draw.material;
            t.low={std::min({t.a.x,t.b.x,t.c.x}),std::min({t.a.y,t.b.y,t.c.y}),std::min({t.a.z,t.b.z,t.c.z})};
            t.high={std::max({t.a.x,t.b.x,t.c.x}),std::max({t.a.y,t.b.y,t.c.y}),std::max({t.a.z,t.b.z,t.c.z})};
            const D3 n=Cross(Sub(D(t.b),D(t.a)),Sub(D(t.c),D(t.a)));const double n2=Dot(n,n);
            if(n2>0){const double inverse=1/std::sqrt(n2);t.normal={float(n.x*inverse),float(n.y*inverse),float(n.z*inverse)};}
            t.floor=n.y>0&&n.y*n.y>=.5*n2;
            if(t.floor)floors.push_back(static_cast<std::uint32_t>(triangles.size()));
            triangles.push_back(t);
        }
    }
    Require(expected==scene.vertices.size(),"collision scene has uncovered vertices");
    triangles_.swap(triangles);floors_.swap(floors);excludedVertexAlpha_=excluded;
}

RayHit CollisionWorld::Raycast(Vec3 start,Vec3 end) const {
    Require(Finite(start)&&Finite(end),"collision ray has nonfinite endpoint");
    const D3 delta=Sub(D(end),D(start));const double length=std::sqrt(Dot(delta,delta));
    Require(length>0&&std::isfinite(length),"collision ray has zero length");
    const D3 direction{delta.x/length,delta.y/length,delta.z/length};RayHit result;double best=length;
    for(const auto& triangle:triangles_) {
        double hit;
        if(!RayTriangle(start,direction,best,triangle.a,triangle.b,triangle.c,hit))continue;
        best=hit;result.hit=true;result.distance=static_cast<float>(hit);result.position={float(start.x+direction.x*hit),float(start.y+direction.y*hit),float(start.z+direction.z*hit)};
        result.normal=triangle.normal;
        if(Dot(D(result.normal),direction)>0){result.normal.x=-result.normal.x;result.normal.y=-result.normal.y;result.normal.z=-result.normal.z;}
        result.triangle=triangle.source;result.material=triangle.material;
    }
    return result;
}

bool CollisionWorld::FindGround(Vec3 feet,float maxRise,float maxDrop,float& height) const {
    Require(Finite(feet)&&std::isfinite(maxRise)&&maxRise>=0&&std::isfinite(maxDrop)&&maxDrop>=0,"collision invalid ground query");
    bool found=false;double best=-std::numeric_limits<double>::infinity();
    const double top=static_cast<double>(feet.y)+maxRise,bottom=static_cast<double>(feet.y)-maxDrop;
    for(const auto index:floors_) {
        const auto& t=triangles_[index];
        if(feet.x<t.low.x||feet.x>t.high.x||feet.z<t.low.z||feet.z>t.high.z||t.low.y>top||t.high.y<bottom)continue;
        const double abx=double(t.b.x)-t.a.x,abz=double(t.b.z)-t.a.z,acx=double(t.c.x)-t.a.x,acz=double(t.c.z)-t.a.z;
        const double px=double(feet.x)-t.a.x,pz=double(feet.z)-t.a.z,det=abx*acz-abz*acx;
        if(det==0)continue;
        const double u=(px*acz-pz*acx)/det,v=(abx*pz-abz*px)/det;
        if(u< -1e-7||v< -1e-7||u+v>1+1e-7)continue;
        const double y=t.a.y+u*(double(t.b.y)-t.a.y)+v*(double(t.c.y)-t.a.y);
        if(y<bottom-1e-6||y>top+1e-6||y<=best)continue;
        best=y;found=true;
    }
    if(found)height=static_cast<float>(best);
    return found;
}

bool CollisionWorld::Supported(Vec3 feet,float radius,float rise,float drop,float& y) const {
    constexpr float directions[9][2]={{0,0},{1,0},{-1,0},{0,1},{0,-1},{.70710678f,.70710678f},{-.70710678f,.70710678f},{.70710678f,-.70710678f},{-.70710678f,-.70710678f}};
    y=-std::numeric_limits<float>::infinity();
    for(const auto& direction:directions){float sample;if(!FindGround({feet.x+radius*direction[0],feet.y,feet.z+radius*direction[1]},rise,drop,sample))return false;y=std::max(y,sample);}
    return true;
}
bool CollisionWorld::Blocked(Vec3 feet,float radius,float height) const {
    const double radius2=static_cast<double>(radius)*radius;
    for(const auto& t:triangles_) {
        // Supporting floors do not count as a penetrating wall. Elevated
        // walkable surfaces still block the capsule body (e.g. an overhead
        // platform with only an upward-facing visible triangle).
        if((t.floor&&t.high.y<=feet.y+1e-5f)||feet.x+radius<t.low.x||feet.x-radius>t.high.x||feet.z+radius<t.low.z||feet.z-radius>t.high.z||feet.y+height<t.low.y||feet.y>t.high.y)continue;
        if(CapsuleDistance(feet,radius,height,t.a,t.b,t.c)<radius2-1e-8)return true;
    }
    return false;
}

MoveResult CollisionWorld::MoveCapsule(Vec3 feet,Vec3 delta,float radius,float height,float stepHeight) const {
    Require(Finite(feet)&&Finite(delta)&&std::isfinite(radius)&&radius>0&&std::isfinite(height)&&height>=2*radius&&
            std::isfinite(stepHeight)&&stepHeight>=0&&stepHeight<=height,"collision invalid capsule movement");
    const double length=std::sqrt(Dot(D(delta),D(delta))),spacing=std::min(double(radius)*.4,.1);
    const double count=std::ceil(length/spacing);Require(std::isfinite(count)&&count<=4096,"collision movement delta exceeds bounded sweep");
    const unsigned steps=static_cast<unsigned>(std::max(1.0,count));
    const Vec3 increment{delta.x/steps,delta.y/steps,delta.z/steps};MoveResult result;result.position=feet;
    const auto attempt=[&](Vec3 desired,bool& floorBlocked,bool& wallBlocked,float& ground) {
        if(!Supported(desired,radius,stepHeight,stepHeight+.05f,ground)){floorBlocked=true;return false;}
        desired.y=ground;if(Blocked(desired,radius,height)){wallBlocked=true;return false;}return true;
    };
    for(unsigned step=0;step<steps;step++) {
        const Vec3 before=result.position;const Vec3 desired{before.x+increment.x,before.y+increment.y,before.z+increment.z};float ground;
        if(attempt(desired,result.floorBlocked,result.wallBlocked,ground))result.position={desired.x,ground,desired.z};
        else {
            if(increment.x!=0&&attempt({before.x+increment.x,before.y+increment.y,before.z},result.floorBlocked,result.wallBlocked,ground))result.position={before.x+increment.x,ground,before.z};
            const Vec3 afterX=result.position;
            if(increment.z!=0&&attempt({afterX.x,before.y+increment.y,before.z+increment.z},result.floorBlocked,result.wallBlocked,ground))result.position={afterX.x,ground,before.z+increment.z};
        }
        result.stepped=result.stepped||result.position.y>before.y+.001f;
    }
    float ground;result.grounded=Supported(result.position,radius,.002f,.05f,ground)&&!Blocked(result.position,radius,height);
    return result;
}
} // namespace T3BCombat
