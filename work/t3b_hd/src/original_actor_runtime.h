/* Original 11-source-bone actor replay. Include after aya_source_skin.h.
   This replaces the stand-in appearance and hit surface, not original AI or
   hit/death state transitions. Recorded sample time clamps without an invented
   loop. The exporter has already selected the original axis and floor policy. */
#include "combat_triangle.h"

static SourceSkin g_original_actor_source;
static V3 *g_original_actor_world_vertices;
static V3 g_original_actor_lo,g_original_actor_hi;
static float g_original_actor_t;
static int g_original_actor_pose_valid;
static unsigned g_original_actor_pose_updates,g_original_actor_draws;
static unsigned g_original_actor_ray_queries,g_original_actor_triangle_checks;
static float g_original_actor_render_mesh_max_error;
static unsigned g_original_actor_render_mesh_sync_failures;
static void load_original_actor(void){
    SourceSkin*s=&g_original_actor_source;
    if(!load_source_skin(s,"assets/models/original_actor_source.bin","assets/materials/original_actor/original_actor_materials.txt"))return;
    if(s->bones!=11||s->packets!=28||s->vertices!=1800||s->time[0]!=0||!g_aya_source.ok||s->units!=g_aya_source.units){
        fprintf(stderr,"[original-actor] rejected incompatible original source geometry or canonical scale\n");free_source_skin(s);return;
    }
    g_original_actor_world_vertices=calloc(s->vertices,sizeof *g_original_actor_world_vertices);
    if(!g_original_actor_world_vertices)die("original actor posed mesh allocation failed");
}
static void pose_original_actor(const Actor*actor,float dt){
    SourceSkin*s=&g_original_actor_source;if(!s->ok)return;
    if(!actor->dead&&dt>0)g_original_actor_t+=dt;
    if(g_original_actor_t>s->duration)g_original_actor_t=s->duration;
    pose_source_skin(s,g_original_actor_t);
    g_original_actor_lo=(V3){1e30f,1e30f,1e30f};g_original_actor_hi=(V3){-1e30f,-1e30f,-1e30f};
    for(uint32_t i=0;i<s->vertices;i++){
        V3 p=source_actor_world(s,actor->x,actor->z,actor->yaw,s->posed[i]);g_original_actor_world_vertices[i]=p;
        if(p.x<g_original_actor_lo.x)g_original_actor_lo.x=p.x;
        if(p.y<g_original_actor_lo.y)g_original_actor_lo.y=p.y;
        if(p.z<g_original_actor_lo.z)g_original_actor_lo.z=p.z;
        if(p.x>g_original_actor_hi.x)g_original_actor_hi.x=p.x;
        if(p.y>g_original_actor_hi.y)g_original_actor_hi.y=p.y;
        if(p.z>g_original_actor_hi.z)g_original_actor_hi.z=p.z;
    }
    g_original_actor_pose_valid=1;g_original_actor_pose_updates++;
}
static int ray_original_actor(V3 origin,V3 direction,float max_t,float*out_t){
    SourceSkin*s=&g_original_actor_source;
    if(!s->ok||!g_original_actor_pose_valid)return 0;
    g_original_actor_ray_queries++;int hit=0;float best=max_t;
    for(uint32_t i=0;i<s->vertices;i+=3){
        V3 a=g_original_actor_world_vertices[i],b=g_original_actor_world_vertices[i+1],c=g_original_actor_world_vertices[i+2];
        g_original_actor_triangle_checks++;
        if(combat_ray_triangle((CombatRay3){origin.x,origin.y,origin.z},(CombatRay3){direction.x,direction.y,direction.z},0,best,
            (CombatRay3){a.x,a.y,a.z},(CombatRay3){b.x,b.y,b.z},(CombatRay3){c.x,c.y,c.z},&best))hit=1;
    }
    if(hit&&out_t)*out_t=best;
    return hit;
}
static void draw_original_actor(const Actor*actor){
    if(!g_original_actor_source.ok||!g_original_actor_pose_valid)return;
    draw_source_skin(&g_original_actor_source,actor->x,actor->z,actor->yaw,g_original_actor_t);g_original_actor_draws++;
    /* Verify that the exact posed positions just sent to rendering agree
       with the world-space triangle cache used by this frame's shot. */
    for(uint32_t i=0;i<g_original_actor_source.vertices;i++){
        V3 p=source_actor_world(&g_original_actor_source,actor->x,actor->z,actor->yaw,g_original_actor_source.posed[i]);
        V3 q=g_original_actor_world_vertices[i];
        float error=(!isfinite(p.x)||!isfinite(p.y)||!isfinite(p.z)||!isfinite(q.x)||!isfinite(q.y)||!isfinite(q.z))?INFINITY:
            fmaxf(fabsf(p.x-q.x),fmaxf(fabsf(p.y-q.y),fabsf(p.z-q.z)));
        if(!isfinite(error)){g_original_actor_render_mesh_sync_failures++;g_original_actor_render_mesh_max_error=INFINITY;}
        else{if(error>g_original_actor_render_mesh_max_error)g_original_actor_render_mesh_max_error=error;if(error!=0)g_original_actor_render_mesh_sync_failures++;}
    }
}
static void write_original_actor_result(FILE*f){
    SourceSkin*s=&g_original_actor_source;
    fprintf(f,"original_enemy_enabled=%d\noriginal_enemy_bones=%u\noriginal_enemy_packets=%u\noriginal_enemy_vertices=%u\noriginal_enemy_triangles=%u\noriginal_enemy_samples=%u\noriginal_enemy_time=%.9g\noriginal_enemy_duration=%.9g\noriginal_enemy_units=%.9g\noriginal_enemy_floor=%.9g\noriginal_enemy_pose_updates=%u\noriginal_enemy_draws=%u\noriginal_enemy_mesh_ray_queries=%u\noriginal_enemy_mesh_triangle_checks=%u\nenemy_hit_geometry=%s\noriginal_enemy_ai_recovered=0\noriginal_enemy_hit_animation_recovered=0\noriginal_enemy_death_animation_recovered=0\noriginal_enemy_playback_clamp=1\n",s->ok,s->bones,s->packets,s->vertices,s->vertices/3,s->frames,g_original_actor_t,s->duration,s->units,s->floor,g_original_actor_pose_updates,g_original_actor_draws,g_original_actor_ray_queries,g_original_actor_triangle_checks,s->ok?"posed_original_source_triangles":"guard_capsule_adapter");
    if(g_original_actor_pose_valid)fprintf(f,"original_enemy_world_bbox=%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n",g_original_actor_lo.x,g_original_actor_lo.y,g_original_actor_lo.z,g_original_actor_hi.x,g_original_actor_hi.y,g_original_actor_hi.z);
    fprintf(f,"original_enemy_render_hit_mesh_max_error=%.9g\noriginal_enemy_render_hit_mesh_sync_failures=%u\n",g_original_actor_render_mesh_max_error,g_original_actor_render_mesh_sync_failures);
}
static void free_original_actor(void){free(g_original_actor_world_vertices);g_original_actor_world_vertices=NULL;free_source_skin(&g_original_actor_source);}
