#ifndef T3B_COMBAT_TRIANGLE_H
#define T3B_COMBAT_TRIANGLE_H

#include "combat_ray.h"

/* Double-sided ray / triangle surface intersection over a closed world-distance
   interval. The input direction must be normalized; the model is never enlarged.
   Collinear triangles, parallel/coplanar rays, and invalid inputs are misses.
   A miss leaves *out_t unchanged; an existence query may pass NULL. */
static inline int combat_ray_triangle(CombatRay3 origin,CombatRay3 direction,
    float min_t,float max_t,CombatRay3 a,CombatRay3 b,CombatRay3 c,float*out_t){
    const float finite_values[]={origin.x,origin.y,origin.z,direction.x,direction.y,direction.z,
        min_t,max_t,a.x,a.y,a.z,b.x,b.y,b.z,c.x,c.y,c.z};
    for(unsigned i=0;i<sizeof finite_values/sizeof finite_values[0];i++)if(!isfinite(finite_values[i]))return 0;
    if(min_t<0||max_t<min_t)return 0;
    double dx=direction.x,dy=direction.y,dz=direction.z;
    if(fabs(dx*dx+dy*dy+dz*dz-1)>1e-4)return 0;
    double e1x=(double)b.x-a.x,e1y=(double)b.y-a.y,e1z=(double)b.z-a.z;
    double e2x=(double)c.x-a.x,e2y=(double)c.y-a.y,e2z=(double)c.z-a.z;
    double px=dy*e2z-dz*e2y,py=dz*e2x-dx*e2z,pz=dx*e2y-dy*e2x;
    double determinant=e1x*px+e1y*py+e1z*pz;
    double scale=sqrt((e1x*e1x+e1y*e1y+e1z*e1z)*(e2x*e2x+e2y*e2y+e2z*e2z));
    if(scale==0||fabs(determinant)<=16*DBL_EPSILON*scale)return 0;
    double tx=(double)origin.x-a.x,ty=(double)origin.y-a.y,tz=(double)origin.z-a.z;
    double inverse=1/determinant,u=(tx*px+ty*py+tz*pz)*inverse;
    if(u<0||u>1)return 0;
    double qx=ty*e1z-tz*e1y,qy=tz*e1x-tx*e1z,qz=tx*e1y-ty*e1x;
    double v=(dx*qx+dy*qy+dz*qz)*inverse;
    if(v<0||u+v>1)return 0;
    double t=(e2x*qx+e2y*qy+e2z*qz)*inverse;
    if(t<min_t||t>max_t)return 0;
    if(out_t)*out_t=(float)t;
    return 1;
}

#endif
