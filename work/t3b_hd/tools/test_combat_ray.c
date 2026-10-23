#include "../src/combat_ray.h"
#include <stdio.h>
#include <stdlib.h>

static unsigned checks,failures;
static void check_hit(const char*label,CombatRay3 origin,CombatRay3 direction,
                     float near_t,float far_t,float y_min,float y_max,float radius,float expected){
    float t=-123;int hit=combat_ray_vertical_capsule(origin,direction,near_t,far_t,0,0,y_min,y_max,radius,&t);
    checks++;
    if(!hit||fabsf(t-expected)>2e-5f){fprintf(stderr,"FAIL %s: hit=%d t=%.9g expected=%.9g\n",label,hit,t,expected);failures++;}
}
static void check_miss(const char*label,CombatRay3 origin,CombatRay3 direction,
                      float near_t,float far_t,float y_min,float y_max,float radius){
    float t=-123;int hit=combat_ray_vertical_capsule(origin,direction,near_t,far_t,0,0,y_min,y_max,radius,&t);
    checks++;
    if(hit||t!=-123){fprintf(stderr,"FAIL %s: hit=%d t=%.9g (miss must preserve output)\n",label,hit,t);failures++;}
}
int main(void){
    CombatRay3 forward={0,0,1};
    check_hit("cylinder front",(CombatRay3){0,1,-5},forward,0,10,0,2,1,4);
    check_hit("diagonal cylinder",(CombatRay3){-3,1,-4},(CombatRay3){.6f,0,.8f},0,10,0,2,1,4);
    check_miss("lateral miss",(CombatRay3){1.01f,1,-5},forward,0,10,0,2,1);
    check_miss("above miss",(CombatRay3){0,3.01f,-5},forward,0,10,0,2,1);
    check_miss("target behind",(CombatRay3){0,1,5},forward,0,10,0,2,1);
    check_miss("far before entry",(CombatRay3){0,1,-5},forward,0,3.99f,0,2,1);
    check_hit("closed far boundary",(CombatRay3){0,1,-5},forward,0,4,0,2,1,4);
    check_miss("near beyond exit",(CombatRay3){0,1,-5},forward,6.01f,10,0,2,1);
    check_hit("near inside",(CombatRay3){0,1,-5},forward,4.5f,10,0,2,1,4.5f);
    check_hit("closed near boundary",(CombatRay3){0,1,-5},forward,6,10,0,2,1,6);
    check_hit("inside origin",(CombatRay3){0,1,0},forward,0,10,0,2,1,0);
    check_hit("inside cap origin",(CombatRay3){0,2.5f,0},forward,0,10,0,2,1,0);
    check_hit("tangent cylinder",(CombatRay3){1,1,-5},forward,0,10,0,2,1,5);
    check_miss("just outside tangent",(CombatRay3){1.0001f,1,-5},forward,0,10,0,2,1);
    check_hit("upper cap",(CombatRay3){0,2.6f,-5},forward,0,10,0,2,1,4.2f);
    check_hit("lower cap",(CombatRay3){0,-.6f,-5},forward,0,10,0,2,1,4.2f);
    check_hit("diagonal upper cap",(CombatRay3){0,5,-4},(CombatRay3){0,-.6f,.8f},0,10,0,2,1,4);
    check_hit("diagonal lower cap",(CombatRay3){0,-3,-4},(CombatRay3){0,.6f,.8f},0,10,0,2,1,4);
    check_hit("tangent upper cap",(CombatRay3){0,3,-5},forward,0,10,0,2,1,5);
    check_hit("vertical down",(CombatRay3){0,5,0},(CombatRay3){0,-1,0},0,10,0,2,1,2);
    check_hit("vertical up",(CombatRay3){0,-5,0},(CombatRay3){0,1,0},0,10,0,2,1,4);
    check_miss("parallel outside cylinder",(CombatRay3){1.01f,-5,0},(CombatRay3){0,1,0},0,10,0,2,1);
    check_hit("sphere degeneration",(CombatRay3){0,1,-5},forward,0,10,1,1,1,4);
    check_hit("sphere inside",(CombatRay3){0,1,0},forward,0,10,1,1,1,0);
    check_hit("zero interval hit",(CombatRay3){0,1,-5},forward,4,4,0,2,1,4);
    check_miss("zero interval miss",(CombatRay3){0,1,-5},forward,3,3,0,2,1);
    check_miss("negative near",(CombatRay3){0,1,-5},forward,-1,10,0,2,1);
    check_miss("inverted interval",(CombatRay3){0,1,-5},forward,10,1,0,2,1);
    check_miss("negative radius",(CombatRay3){0,1,-5},forward,0,10,0,2,-1);
    check_miss("zero radius",(CombatRay3){0,1,-5},forward,0,10,0,2,0);
    check_miss("inverted endpoints",(CombatRay3){0,1,-5},forward,0,10,2,0,1);
    check_miss("zero direction",(CombatRay3){0,1,-5},(CombatRay3){0,0,0},0,10,0,2,1);
    check_miss("nonnormalized direction",(CombatRay3){0,1,-5},(CombatRay3){0,0,2},0,10,0,2,1);
    check_miss("NaN origin",(CombatRay3){NAN,1,-5},forward,0,10,0,2,1);
    check_miss("infinite direction",(CombatRay3){0,1,-5},(CombatRay3){0,0,INFINITY},0,10,0,2,1);
    check_miss("infinite far",(CombatRay3){0,1,-5},forward,0,INFINITY,0,2,1);
    check_miss("NaN radius",(CombatRay3){0,1,-5},forward,0,10,0,2,NAN);
    check_miss("NaN endpoint",(CombatRay3){0,1,-5},forward,0,10,NAN,2,1);
    /* Translation invariance and optional-output behavior. */
    float translated_t=-1;checks++;
    if(!combat_ray_vertical_capsule((CombatRay3){7,1,-8},forward,0,10,7,-3,0,2,1,&translated_t)||translated_t!=4){fprintf(stderr,"FAIL translated capsule\n");failures++;}
    checks++;
    if(!combat_ray_vertical_capsule((CombatRay3){0,1,-5},forward,0,10,0,0,0,2,1,NULL)){fprintf(stderr,"FAIL null optional output\n");failures++;}
    checks++;translated_t=-123;
    if(combat_ray_vertical_capsule((CombatRay3){0,1,-5},forward,0,10,NAN,0,0,2,1,&translated_t)||translated_t!=-123){fprintf(stderr,"FAIL NaN capsule center\n");failures++;}
    printf("combat_ray_checks=%u\ncombat_ray_failures=%u\n",checks,failures);
    return failures?EXIT_FAILURE:EXIT_SUCCESS;
}
