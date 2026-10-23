#ifndef T3B_COMBAT_RAY_H
#define T3B_COMBAT_RAY_H

#include <float.h>
#include <math.h>

/* All distances are in the same world units. A vertical capsule is the
   Minkowski sum of [(cx, y_min, cz), (cx, y_max, cz)] and a radius sphere.
   The caller supplies a normalized direction: this API does not silently
   change a weapon's direction, radius, or usable ray interval. */
typedef struct { float x, y, z; } CombatRay3;

static inline int combat_ray_quadratic(double a,double b,double c,double roots[2]){
    if(a<=0)return 0;
    double four_ac=4*a*c;
    double discriminant=fma(b,b,-four_ac);
    /* Only compensate for rounding in the discriminant, not target size. */
    double roundoff=16*DBL_EPSILON*(b*b+fabs(four_ac));
    if(discriminant<0){if(discriminant < -roundoff)return 0;discriminant=0;}
    double square_root=sqrt(discriminant);
    if(square_root==0){roots[0]=roots[1]=-b/(2*a);return 1;}
    double q=-.5*(b+copysign(square_root,b));
    roots[0]=q/a;roots[1]=c/q;
    if(roots[0]>roots[1]){double temp=roots[0];roots[0]=roots[1];roots[1]=temp;}
    return 2;
}

/* Return the earliest point IN the capsule over the CLOSED [min_t,max_t]
   interval. Thus an interval starting inside returns min_t. Misses and invalid
   inputs leave *out_t unchanged; out_t may be NULL for an existence query.
   Valid input: finite values, 0 <= min_t <= max_t, y_min <= y_max,
   radius > 0, and |dot(direction,direction)-1| <= 1e-4.
   y_min == y_max is a sphere. Internals use double to reduce float cancellation. */
static inline int combat_ray_vertical_capsule(
    CombatRay3 origin,CombatRay3 direction,float min_t,float max_t,
    float cx,float cz,float y_min,float y_max,float radius,float*out_t){
    if(!isfinite(origin.x)||!isfinite(origin.y)||!isfinite(origin.z)||
       !isfinite(direction.x)||!isfinite(direction.y)||!isfinite(direction.z)||
       !isfinite(min_t)||!isfinite(max_t)||!isfinite(cx)||!isfinite(cz)||
       !isfinite(y_min)||!isfinite(y_max)||!isfinite(radius)||
       min_t<0||max_t<min_t||y_max<y_min||radius<=0)return 0;
    double dx=direction.x,dy=direction.y,dz=direction.z;
    double length_squared=dx*dx+dy*dy+dz*dz;
    if(fabs(length_squared-1)>1e-4)return 0;
    double ox=(double)origin.x-cx,oy=origin.y,oz=(double)origin.z-cz;
    double near_t=min_t,far_t=max_t,r2=(double)radius*radius;
    double px=ox+dx*near_t,py=oy+dy*near_t,pz=oz+dz*near_t;
    double closest_y=py<y_min?y_min:(py>y_max?y_max:py);
    double vertical_delta=py-closest_y;
    if(px*px+pz*pz+vertical_delta*vertical_delta<=r2){if(out_t)*out_t=min_t;return 1;}

    double best=far_t,roots[2];int hit=0;
    /* Cylinder side. The axis-parallel case has no side crossing. */
    int count=combat_ray_quadratic(dx*dx+dz*dz,2*(ox*dx+oz*dz),ox*ox+oz*oz-r2,roots);
    for(int i=0;i<count;i++){
        double t=roots[i],y=oy+dy*t;
        if(t>=near_t&&t<=best&&y>=y_min&&y<=y_max){best=t;hit=1;}
    }
    /* Full endpoint spheres plus the cylinder equal the exact capsule.
       Their overlap cannot introduce an intersection outside the capsule. */
    int cap_count=y_min==y_max?1:2;
    for(int cap=0;cap<cap_count;cap++){
        double sy=oy-(cap?y_max:y_min);
        count=combat_ray_quadratic(length_squared,2*(ox*dx+sy*dy+oz*dz),ox*ox+sy*sy+oz*oz-r2,roots);
        for(int i=0;i<count;i++)if(roots[i]>=near_t&&roots[i]<=best){best=roots[i];hit=1;}
    }
    if(hit&&out_t)*out_t=(float)best;
    return hit;
}

#endif
