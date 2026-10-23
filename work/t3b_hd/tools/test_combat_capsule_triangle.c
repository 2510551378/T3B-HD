#include "../src/combat_capsule_triangle.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned checks,failures;
static void distance_check(const char*name,float x,float z,float y0,float y1,CombatRay3 a,CombatRay3 b,CombatRay3 c,double expected){
    double d=combat_vertical_axis_triangle_distance2(x,z,y0,y1,a,b,c);checks++;
    if(!isfinite(d)||fabs(d-expected)>1e-7){failures++;fprintf(stderr,"FAIL %s distance2=%.12g expected %.12g\n",name,d,expected);}
}
int main(void){
    CombatRay3 a={0,0,-2},b={0,3,-2},c={0,0,2};
    distance_check("wall parallel axis",.5f,0,.2f,1.6f,a,b,c,.25);
    distance_check("wall contact",0,0,.2f,1.6f,a,b,c,0);
    distance_check("wall opposite winding",.5f,0,.2f,1.6f,c,b,a,.25);
    distance_check("above wall",0,-2,4,5,a,b,c,1);
    distance_check("triangle vertex nearest",1,-2,-1,-.5f,a,b,c,1.25);
    distance_check("floor below axis",0,0,.2f,1.6f,(CombatRay3){-2,0,-2},(CombatRay3){0,0,2},(CombatRay3){2,0,-2},.04);
    distance_check("axis pierces roof",0,0,.2f,1.6f,(CombatRay3){-2,1,-2},(CombatRay3){0,1,2},(CombatRay3){2,1,-2},0);
    distance_check("zero-length axis",.5f,0,1,1,a,b,c,.25);
    distance_check("degenerate triangle point",1,0,.2f,1.6f,(CombatRay3){0,1,0},(CombatRay3){0,1,0},(CombatRay3){0,1,0},1);
    distance_check("degenerate triangle segment",1,0,.2f,1.6f,(CombatRay3){0,0,0},(CombatRay3){0,2,0},(CombatRay3){0,1,0},1);
    checks++;if(!isnan(combat_vertical_axis_triangle_distance2(NAN,0,.2f,1.6f,a,b,c))){failures++;fprintf(stderr,"FAIL NaN input\n");}
    checks++;if(!isnan(combat_vertical_axis_triangle_distance2(0,0,2,1,a,b,c))){failures++;fprintf(stderr,"FAIL reversed axis\n");}
    CombatRay3 fa={-1,0,-1},fb={-1,0,1},fc={1,0,1},fd={1,0,-1};
    checks++;if(!combat_point_in_triangle_xz(0,0,fa,fb,fc)||!combat_point_in_triangle_xz(0,0,fa,fc,fd)){failures++;fprintf(stderr,"FAIL floor seam\n");}
    checks++;if(combat_point_in_triangle_xz(1.001f,0,fa,fc,fd)){failures++;fprintf(stderr,"FAIL outside floor\n");}
    checks++;if(!combat_point_in_triangle_xz(.9f,-.9f,fd,fc,fa)){failures++;fprintf(stderr,"FAIL reversed floor winding\n");}
    printf("combat_capsule_triangle_checks=%u\ncombat_capsule_triangle_failures=%u\n",checks,failures);return failures?EXIT_FAILURE:EXIT_SUCCESS;
}
