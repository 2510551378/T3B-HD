#include "../src/combat_triangle.h"
#include <stdio.h>
#include <stdlib.h>

static unsigned checks,failures;
static const CombatRay3 a={-1,-1,3},b={1,-1,3},c={0,1,3};
static void check(const char*label,CombatRay3 origin,CombatRay3 direction,float near_t,float far_t,
                  CombatRay3 va,CombatRay3 vb,CombatRay3 vc,int expected,float expected_t){
    float t=-123;int hit=combat_ray_triangle(origin,direction,near_t,far_t,va,vb,vc,&t);checks++;
    if(hit!=expected||(hit?fabsf(t-expected_t)>1e-5f:t!=-123)){failures++;fprintf(stderr,"FAIL %s: hit=%d t=%.9g expected=%d t=%.9g\n",label,hit,t,expected,expected_t);}
}
int main(void){
    CombatRay3 origin={0,0,0},forward={0,0,1};
    check("front",origin,forward,0,10,a,b,c,1,3);
    check("reverse winding",origin,forward,0,10,a,c,b,1,3);
    check("back",(CombatRay3){0,0,5},(CombatRay3){0,0,-1},0,10,a,b,c,1,2);
    check("vertex a",(CombatRay3){-1,-1,0},forward,0,10,a,b,c,1,3);
    check("vertex c",(CombatRay3){0,1,0},forward,0,10,a,b,c,1,3);
    check("edge",(CombatRay3){0,-1,0},forward,0,10,a,b,c,1,3);
    check("outside edge",(CombatRay3){0,-1.0001f,0},forward,0,10,a,b,c,0,0);
    check("lateral miss",(CombatRay3){2,0,0},forward,0,10,a,b,c,0,0);
    check("above miss",(CombatRay3){0,1.001f,0},forward,0,10,a,b,c,0,0);
    check("behind",(CombatRay3){0,0,5},forward,0,10,a,b,c,0,0);
    check("far cut",origin,forward,0,2.99f,a,b,c,0,0);
    check("near cut",origin,forward,3.01f,10,a,b,c,0,0);
    check("closed single interval",origin,forward,3,3,a,b,c,1,3);
    check("on surface",(CombatRay3){0,0,3},forward,0,10,a,b,c,1,0);
    check("parallel",origin,(CombatRay3){1,0,0},0,10,a,b,c,0,0);
    check("coplanar",(CombatRay3){0,0,3},(CombatRay3){1,0,0},0,10,a,b,c,0,0);
    check("degenerate equal vertices",origin,forward,0,10,a,a,c,0,0);
    check("degenerate collinear",origin,forward,0,10,a,b,(CombatRay3){0,-1,3},0,0);
    check("nonunit",origin,(CombatRay3){0,0,2},0,10,a,b,c,0,0);
    check("zero direction",origin,(CombatRay3){0,0,0},0,10,a,b,c,0,0);
    check("NaN direction",origin,(CombatRay3){NAN,0,1},0,10,a,b,c,0,0);
    check("NaN triangle",origin,forward,0,10,a,b,(CombatRay3){0,NAN,3},0,0);
    check("infinite far",origin,forward,0,INFINITY,a,b,c,0,0);
    check("negative near",origin,forward,-1,10,a,b,c,0,0);
    check("reversed interval",origin,forward,4,2,a,b,c,0,0);
    check("small triangle",origin,forward,0,10,(CombatRay3){-.001f,-.001f,3},(CombatRay3){.001f,-.001f,3},(CombatRay3){0,.001f,3},1,3);
    check("slanted triangle",origin,forward,0,10,(CombatRay3){-1,-1,2},(CombatRay3){1,-1,4},c,1,3);
    checks++;if(!combat_ray_triangle(origin,forward,0,10,a,b,c,NULL)){failures++;fprintf(stderr,"FAIL optional output\n");}
    float nearest=10;int hit_count=0;
    if(combat_ray_triangle(origin,forward,0,nearest,(CombatRay3){-1,-1,6},(CombatRay3){1,-1,6},(CombatRay3){0,1,6},&nearest))hit_count++;
    if(combat_ray_triangle(origin,forward,0,nearest,a,b,c,&nearest))hit_count++;
    checks++;if(hit_count!=2||nearest!=3){failures++;fprintf(stderr,"FAIL nearest triangle distance\n");}
    checks++;if(!combat_ray_triangle(origin,forward,0,10,(CombatRay3){-1,-1,3},(CombatRay3){1,-1,3},(CombatRay3){1,1,3},NULL)||
                !combat_ray_triangle(origin,forward,0,10,(CombatRay3){-1,-1,3},(CombatRay3){1,1,3},(CombatRay3){-1,1,3},NULL)){failures++;fprintf(stderr,"FAIL shared-edge seam\n");}
    printf("combat_triangle_checks=%u\ncombat_triangle_failures=%u\n",checks,failures);
    return failures?EXIT_FAILURE:EXIT_SUCCESS;
}
