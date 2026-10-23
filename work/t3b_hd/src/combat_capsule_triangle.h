#ifndef T3B_COMBAT_CAPSULE_TRIANGLE_H
#define T3B_COMBAT_CAPSULE_TRIANGLE_H
#include "combat_triangle.h"
#include <stddef.h>

typedef struct { double x,y,z; } CombatD3;
static inline CombatD3 combat_d3(CombatRay3 p){return (CombatD3){p.x,p.y,p.z};}
static inline CombatD3 combat_dsub(CombatD3 a,CombatD3 b){return (CombatD3){a.x-b.x,a.y-b.y,a.z-b.z};}
static inline CombatD3 combat_daddscale(CombatD3 a,CombatD3 b,double s){return (CombatD3){a.x+b.x*s,a.y+b.y*s,a.z+b.z*s};}
static inline double combat_ddot(CombatD3 a,CombatD3 b){return a.x*b.x+a.y*b.y+a.z*b.z;}
static inline double combat_dclamp(double x){return x<0?0:(x>1?1:x);}
static inline double combat_point_segment_distance2(CombatD3 p,CombatD3 a,CombatD3 b){
    CombatD3 ab=combat_dsub(b,a),ap=combat_dsub(p,a);double length=combat_ddot(ab,ab);
    CombatD3 delta=combat_dsub(p,combat_daddscale(a,ab,length>0?combat_dclamp(combat_ddot(ap,ab)/length):0));return combat_ddot(delta,delta);
}
static inline double combat_segment_distance2(CombatD3 p1,CombatD3 q1,CombatD3 p2,CombatD3 q2){
    CombatD3 d1=combat_dsub(q1,p1),d2=combat_dsub(q2,p2),r=combat_dsub(p1,p2);
    double a=combat_ddot(d1,d1),e=combat_ddot(d2,d2),f=combat_ddot(d2,r),s=0,t=0;
    if(a==0&&e==0)return combat_ddot(r,r);
    if(a==0)t=combat_dclamp(f/e);
    else{double c=combat_ddot(d1,r);if(e==0)s=combat_dclamp(-c/a);
        else{double b=combat_ddot(d1,d2),denominator=a*e-b*b;
            if(denominator>0)s=combat_dclamp((b*f-c*e)/denominator);
            t=(b*s+f)/e;if(t<0){t=0;s=combat_dclamp(-c/a);}else if(t>1){t=1;s=combat_dclamp((b-c)/a);}
        }
    }
    CombatD3 delta=combat_dsub(combat_daddscale(p1,d1,s),combat_daddscale(p2,d2,t));return combat_ddot(delta,delta);
}
static inline double combat_point_triangle_distance2(CombatD3 p,CombatD3 a,CombatD3 b,CombatD3 c){
    CombatD3 ab=combat_dsub(b,a),ac=combat_dsub(c,a),ap=combat_dsub(p,a);
    CombatD3 normal={ab.y*ac.z-ab.z*ac.y,ab.z*ac.x-ab.x*ac.z,ab.x*ac.y-ab.y*ac.x};
    if(combat_ddot(normal,normal)==0)return fmin(combat_point_segment_distance2(p,a,b),fmin(combat_point_segment_distance2(p,b,c),combat_point_segment_distance2(p,c,a)));
    double d1=combat_ddot(ab,ap),d2=combat_ddot(ac,ap);if(d1<=0&&d2<=0)return combat_ddot(ap,ap);
    CombatD3 bp=combat_dsub(p,b);double d3=combat_ddot(ab,bp),d4=combat_ddot(ac,bp);if(d3>=0&&d4<=d3)return combat_ddot(bp,bp);
    double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0){CombatD3 delta=combat_dsub(p,combat_daddscale(a,ab,d1/(d1-d3)));return combat_ddot(delta,delta);}
    CombatD3 cp=combat_dsub(p,c);double d5=combat_ddot(ab,cp),d6=combat_ddot(ac,cp);if(d6>=0&&d5<=d6)return combat_ddot(cp,cp);
    double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0){CombatD3 delta=combat_dsub(p,combat_daddscale(a,ac,d2/(d2-d6)));return combat_ddot(delta,delta);}
    double va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0){CombatD3 bc=combat_dsub(c,b);CombatD3 delta=combat_dsub(p,combat_daddscale(b,bc,(d4-d3)/((d4-d3)+(d5-d6))));return combat_ddot(delta,delta);}
    double inverse=1/(va+vb+vc);CombatD3 closest=combat_daddscale(combat_daddscale(a,ab,vb*inverse),ac,vc*inverse);
    CombatD3 delta=combat_dsub(p,closest);return combat_ddot(delta,delta);
}
static inline double combat_vertical_axis_triangle_distance2(float x,float z,float y_min,float y_max,CombatRay3 a,CombatRay3 b,CombatRay3 c){
    const float values[]={x,z,y_min,y_max,a.x,a.y,a.z,b.x,b.y,b.z,c.x,c.y,c.z};
    for(unsigned i=0;i<sizeof values/sizeof values[0];i++)if(!isfinite(values[i]))return NAN;
    if(y_max<y_min)return NAN;
    CombatRay3 lower={x,y_min,z},upper={x,y_max,z};
    if(y_max>y_min&&combat_ray_triangle(lower,(CombatRay3){0,1,0},0,y_max-y_min,a,b,c,NULL))return 0;
    CombatD3 p=combat_d3(lower),q=combat_d3(upper),da=combat_d3(a),db=combat_d3(b),dc=combat_d3(c);
    double best=fmin(combat_point_triangle_distance2(p,da,db,dc),combat_point_triangle_distance2(q,da,db,dc));
    best=fmin(best,combat_segment_distance2(p,q,da,db));best=fmin(best,combat_segment_distance2(p,q,db,dc));return fmin(best,combat_segment_distance2(p,q,dc,da));
}
static inline int combat_point_in_triangle_xz(float x,float z,CombatRay3 a,CombatRay3 b,CombatRay3 c){
    double abx=(double)b.x-a.x,abz=(double)b.z-a.z,acx=(double)c.x-a.x,acz=(double)c.z-a.z;
    double px=(double)x-a.x,pz=(double)z-a.z,det=abx*acz-abz*acx;
    if(!isfinite(det)||det==0||!isfinite(x)||!isfinite(z))return 0;
    double u=(px*acz-pz*acx)/det,v=(abx*pz-abz*px)/det;return u>=0&&v>=0&&u+v<=1;
}
#endif
