/* Explicit PC adapter derived from visible static geometry. This is not the
   game's collision format. Cutout/blended/non-depth-writing materials are
   conservatively excluded rather than becoming invisible rectangular walls. */
#include "combat_capsule_triangle.h"
typedef struct { uint32_t vertex,material;int floor;V3 lo,hi; } SourceSolidTriangle;
typedef struct {
    SourceSolidTriangle *triangle;uint32_t *ground;
    uint32_t triangles,floors,solid_materials,excluded_state_materials,excluded_cutout_materials,excluded_cutout_triangles,excluded_vertex_alpha_triangles;
    unsigned ray_queries,ray_hits,movement_queries,movement_floor_blocked,movement_wall_blocked;
    int enabled;
} OriginalSceneCollision;
static OriginalSceneCollision g_source_collision;
static const char*source_collision_name(void){return g_source_collision.enabled?"original_visible_static_triangles":"legacy_columns";}
/* Matches the renderer's decoded 24/32-bit BGRA BMP semantics. All-positive
   alpha suffices for blend-off + alpha>0, including nonzero partial alpha. */
static int source_collision_alpha_proof(const char*path){
    size_t size=0;uint8_t*d=read_file(path,&size);if(!d||size<54||d[0]!='B'||d[1]!='M'){free(d);return -1;}
    uint32_t off=rd32(d+10),dib=rd32(d+14),compression=rd32(d+30);int32_t width=(int32_t)rd32(d+18),raw_height=(int32_t)rd32(d+22);uint16_t bits=rd16(d+28);
    int masks=compression==3&&bits==32&&dib>=108&&size>=122&&rd32(d+54)==0x00ff0000&&rd32(d+58)==0x0000ff00&&rd32(d+62)==0x000000ff&&rd32(d+66)==0xff000000;
    if(dib<40||width<=0||width>16384||raw_height==0||raw_height==INT32_MIN||abs(raw_height)>16384||(bits!=24&&bits!=32)||(compression!=0&&!masks)){free(d);return -1;}
    size_t height=(size_t)abs(raw_height),row=((size_t)width*(bits/8)+3)&~(size_t)3;
    if(off>size||row*height>size-off){free(d);return -1;}
    if(bits==32)for(size_t y=0;y<height;y++)for(int x=0;x<width;x++)if(d[off+y*row+(size_t)x*4+3]==0){free(d);return 0;}
    free(d);return 1;
}
static void free_source_collision(void){free(g_source_collision.triangle);free(g_source_collision.ground);memset(&g_source_collision,0,sizeof g_source_collision);g_original_scene_collision_adapter_enabled=0;}
static int load_source_collision(void){
    OriginalScene*s=&g_original_scene;OriginalSceneCollision*c=&g_source_collision;if(!s->ok)return 0;
    uint8_t*solid=calloc(s->materials,1);c->triangle=calloc(s->vertices/3,sizeof *c->triangle);c->ground=calloc(s->vertices/3,sizeof *c->ground);
    if(!solid||!c->triangle||!c->ground)die("source collision allocation failed");
    FILE*f=fopen("assets/scenes/original_street/original_street_materials.txt","rb");char tag[32];unsigned count=0;int valid=f&&fscanf(f,"%31s %u",tag,&count)==2&&!strcmp(tag,"T3BSCNM1")&&count==s->materials;
    for(uint32_t i=0;i<s->materials&&valid;i++){
        char path[512];int blend,depth,cull;
        if(fscanf(f,"%511s %d %d %d",path,&blend,&depth,&cull)!=4||blend!=s->material[i].blend||depth!=s->material[i].depth_write||cull!=s->material[i].cull||!original_scene_relative_path(path)){valid=0;break;}
        if(blend||!depth){c->excluded_state_materials++;continue;}
        int proof=source_collision_alpha_proof(path);if(proof<0){valid=0;break;}
        if(proof){solid[i]=1;c->solid_materials++;}else c->excluded_cutout_materials++;
    }
    if(f)fclose(f);
    if(!valid){free(solid);free_source_collision();return 0;}
    for(uint32_t draw=0;draw<s->draws;draw++){
        OriginalSceneDraw*q=&s->draw[draw];OriginalSceneMaterial*m=&s->material[q->material];
        for(uint32_t j=q->first;j<q->first+q->count;j+=3){
            if(!solid[q->material]){if(!m->blend&&m->depth_write)c->excluded_cutout_triangles++;continue;}
            if(!s->v[j].rgba[3]||!s->v[j+1].rgba[3]||!s->v[j+2].rgba[3]){c->excluded_vertex_alpha_triangles++;continue;}
            V3 a=s->v[j].p,b=s->v[j+1].p,d=s->v[j+2].p;SourceSolidTriangle*t=&c->triangle[c->triangles];t->vertex=j;t->material=q->material;
            t->lo=(V3){fminf(a.x,fminf(b.x,d.x)),fminf(a.y,fminf(b.y,d.y)),fminf(a.z,fminf(b.z,d.z))};
            t->hi=(V3){fmaxf(a.x,fmaxf(b.x,d.x)),fmaxf(a.y,fmaxf(b.y,d.y)),fmaxf(a.z,fmaxf(b.z,d.z))};
            V3 n=cross(sub(b,a),sub(d,a));double norm2=(double)n.x*n.x+(double)n.y*n.y+(double)n.z*n.z;
            t->floor=n.y>0&&(double)n.y*n.y>=.5*norm2&&fabsf(t->lo.y)<=.05f&&fabsf(t->hi.y)<=.05f;
            if(t->floor)c->ground[c->floors++]=c->triangles;
            c->triangles++;
        }
    }
    free(solid);if(!c->triangles||!c->floors){free_source_collision();return 0;}c->enabled=1;g_original_scene_collision_adapter_enabled=1;
    fprintf(stdout,"[source-collision] PC visible-static adapter: %u alpha-proven materials, %u solid triangles, %u near-ground floor triangles; cutout triangles excluded=%u\n",c->solid_materials,c->triangles,c->floors,c->excluded_cutout_triangles);return 1;
}
static int source_static_ray(V3 origin,V3 direction,float range,float*out_t){
    OriginalSceneCollision*c=&g_source_collision;if(!c->enabled)return 0;c->ray_queries++;float best=range;int hit=0;
    for(uint32_t i=0;i<c->triangles;i++){
        uint32_t v=c->triangle[i].vertex;V3 a=g_original_scene.v[v].p,b=g_original_scene.v[v+1].p,d=g_original_scene.v[v+2].p;
        if(combat_ray_triangle((CombatRay3){origin.x,origin.y,origin.z},(CombatRay3){direction.x,direction.y,direction.z},0,best,(CombatRay3){a.x,a.y,a.z},(CombatRay3){b.x,b.y,b.z},(CombatRay3){d.x,d.y,d.z},&best))hit=1;
    }
    if(hit){c->ray_hits++;if(out_t)*out_t=best;}return hit;
}
static int source_floor_at(float x,float z){
    OriginalSceneCollision*c=&g_source_collision;
    for(uint32_t i=0;i<c->floors;i++){
        SourceSolidTriangle*t=&c->triangle[c->ground[i]];if(x<t->lo.x||x>t->hi.x||z<t->lo.z||z>t->hi.z)continue;
        uint32_t v=t->vertex;V3 a=g_original_scene.v[v].p,b=g_original_scene.v[v+1].p,d=g_original_scene.v[v+2].p;
        if(combat_point_in_triangle_xz(x,z,(CombatRay3){a.x,a.y,a.z},(CombatRay3){b.x,b.y,b.z},(CombatRay3){d.x,d.y,d.z}))return 1;
    }return 0;
}
static int source_floor_disc_supported(float x,float z,float radius){
    const float directions[9][2]={{0,0},{1,0},{-1,0},{0,1},{0,-1},{.70710678f,.70710678f},{-.70710678f,.70710678f},{.70710678f,-.70710678f},{-.70710678f,-.70710678f}};
    for(int i=0;i<9;i++)if(!source_floor_at(x+radius*directions[i][0],z+radius*directions[i][1]))return 0;
    return 1;
}
static int source_walk_blocked(float x,float z,float radius){
    OriginalSceneCollision*c=&g_source_collision;c->movement_queries++;
    if(!isfinite(x)||!isfinite(z)||!isfinite(radius)||radius<=0||radius>=.92f)return 1;
    if(!source_floor_disc_supported(x,z,radius)){c->movement_floor_blocked++;return 1;}
    float low=radius,high=1.84f-radius;
    for(uint32_t i=0;i<c->triangles;i++){
        SourceSolidTriangle*t=&c->triangle[i];if(t->floor||x+radius<t->lo.x||x-radius>t->hi.x||z+radius<t->lo.z||z-radius>t->hi.z||high+radius<t->lo.y||low-radius>t->hi.y)continue;
        uint32_t v=t->vertex;V3 a=g_original_scene.v[v].p,b=g_original_scene.v[v+1].p,d=g_original_scene.v[v+2].p;
        double distance=combat_vertical_axis_triangle_distance2(x,z,low,high,(CombatRay3){a.x,a.y,a.z},(CombatRay3){b.x,b.y,b.z},(CombatRay3){d.x,d.y,d.z});
        if(!isfinite(distance)||distance<(double)radius*radius){c->movement_wall_blocked++;return 1;}
    }return 0;
}
static void write_source_collision_probe(void){
    if(!g_source_collision.enabled)return;
    FILE*f=fopen("build/original_scene_solid_triangles.csv","wb");if(!f)return;
    fprintf(f,"triangle,vertex_first,material,ground_adapter\n");for(uint32_t i=0;i<g_source_collision.triangles;i++){SourceSolidTriangle*t=&g_source_collision.triangle[i];fprintf(f,"%u,%u,%u,%d\n",t->vertex/3,t->vertex,t->material,t->floor);}fclose(f);
}
static void write_source_collision_result(FILE*f){
    OriginalSceneCollision*c=&g_source_collision;
    fprintf(f,"collision_recovered=0\ncollision_adapter_source=%s\nshooting_collision_adapter=%s\nmovement_collision_adapter=%s\ncollision_solid_materials=%u\ncollision_solid_triangles=%u\ncollision_floor_triangles=%u\ncollision_excluded_state_materials=%u\ncollision_excluded_cutout_materials=%u\ncollision_excluded_cutout_triangles=%u\ncollision_excluded_vertex_alpha_triangles=%u\ncollision_alpha_policy=all_texture_texels_and_all_triangle_vertex_alpha_positive\ncollision_ray_queries=%u\ncollision_ray_hits=%u\ncollision_movement_queries=%u\ncollision_movement_floor_blocked=%u\ncollision_movement_wall_blocked=%u\ncollision_step_climb_recovered=0\ncollision_floor_coverage_samples=9\ncollision_capsule_height=1.84\n",source_collision_name(),c->enabled?"nearest_static_source_triangle":"legacy_columns",c->enabled?"near_ground_union_9_samples_capsule_triangle_distance":"legacy_columns",c->solid_materials,c->triangles,c->floors,c->excluded_state_materials,c->excluded_cutout_materials,c->excluded_cutout_triangles,c->excluded_vertex_alpha_triangles,c->ray_queries,c->ray_hits,c->movement_queries,c->movement_floor_blocked,c->movement_wall_blocked);
    fprintf(f,"scene_collision=%s\ncollision_adapter=%s\n",source_collision_name(),source_collision_name());
}
