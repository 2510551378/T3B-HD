#include <SDL.h>
#include <SDL_opengl.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "combat_ray.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct { float x, y, z; } V3;
typedef struct { float u, v; } V2;
typedef struct { int a, b, c; int ua, ub, uc; } Tri;
typedef struct { V3 *v; size_t nv, cv; V2 *uv; size_t nuv, cuv; Tri *t; size_t nt, ct; int has_uv; V3 lo, hi, center; } Obj;
typedef struct { char name[16]; uint16_t first, count, loop; float fps; } Clip;
typedef struct { uint8_t *file; int ok, N, M, K, nclip; float scale[3], off[3]; uint16_t *idx; uint8_t *keys; uint32_t kb; Clip clips[16]; } Pmf;
typedef struct { float x, z, yaw, hp; int dead, locked; float fire_cd, hit_t, shoot_t, anim_t, ge_t; } Actor;

static void die(const char *msg) { fprintf(stderr, "[t3b_hd] %s\n", msg); exit(1); }
static void *grow(void *p, size_t *cap, size_t need, size_t elem) {
    if (need <= *cap) return p;
    size_t n = *cap ? *cap : 4096; while (n < need) n *= 2;
    void *q = realloc(p, n * elem); if (!q) die("out of memory"); *cap = n; return q;
}
static int obj_index(const char *s, int n) { char *e=NULL; long k=strtol(s,&e,10); if(e==s||k==0)return -1; if(k<0)k=(long)n+k+1; return (int)k-1; }
static void face_indices(char *tok, int nv, int nuv, int *vi, int *ui) {
    *vi = *ui = -1;
    char *slash = strchr(tok, '/');
    if (!slash) { *vi = obj_index(tok, nv); return; }
    *slash = 0; *vi = obj_index(tok, nv);
    char *uv = slash + 1; char *slash2 = strchr(uv, '/'); if (slash2) *slash2 = 0;
    if (*uv) *ui = obj_index(uv, nuv);
}
static Obj load_obj(const char *path) {
    Obj o; memset(&o,0,sizeof o); o.lo=(V3){1e30f,1e30f,1e30f}; o.hi=(V3){-1e30f,-1e30f,-1e30f};
    FILE *f=fopen(path,"rb"); if(!f){fprintf(stderr,"[asset] missing %s\n",path);exit(1);} char line[1024];
    while(fgets(line,sizeof line,f)) {
        if(line[0]=='v'&&line[1]==' ') { V3 p; if(sscanf(line+2,"%f %f %f",&p.x,&p.y,&p.z)!=3)continue; o.v=grow(o.v,&o.cv,o.nv+1,sizeof *o.v);o.v[o.nv++]=p;
            if(p.x<o.lo.x)o.lo.x=p.x;
            if(p.y<o.lo.y)o.lo.y=p.y;
            if(p.z<o.lo.z)o.lo.z=p.z;
            if(p.x>o.hi.x)o.hi.x=p.x;
            if(p.y>o.hi.y)o.hi.y=p.y;
            if(p.z>o.hi.z)o.hi.z=p.z;
        } else if(line[0]=='v'&&line[1]=='t'&&line[2]==' ') { V2 uv; if(sscanf(line+3,"%f %f",&uv.u,&uv.v)!=2)continue; o.uv=grow(o.uv,&o.cuv,o.nuv+1,sizeof *o.uv);o.uv[o.nuv++]=uv; o.has_uv=1;
        } else if(line[0]=='f'&&line[1]==' ') {
            char a[64],b[64],c[64],d[64]; int n=sscanf(line+2,"%63s %63s %63s %63s",a,b,c,d); if(n<3)continue;
            int ia,ib,ic,ua,ub,uc; face_indices(a,(int)o.nv,(int)o.nuv,&ia,&ua); face_indices(b,(int)o.nv,(int)o.nuv,&ib,&ub); face_indices(c,(int)o.nv,(int)o.nuv,&ic,&uc);
            if(ia<0||ib<0||ic<0||ia>=(int)o.nv||ib>=(int)o.nv||ic>=(int)o.nv)continue;
            o.t=grow(o.t,&o.ct,o.nt+1,sizeof *o.t); o.t[o.nt++]=(Tri){ia,ib,ic,ua,ub,uc};
            if(n==4){int id,ud; face_indices(d,(int)o.nv,(int)o.nuv,&id,&ud); if(id>=0&&id<(int)o.nv){o.t=grow(o.t,&o.ct,o.nt+1,sizeof *o.t);o.t[o.nt++]=(Tri){ia,ic,id,ua,uc,ud};}}
        }
    }
    fclose(f); if(!o.nv||!o.nt)die("OBJ has no geometry"); o.center=(V3){(o.lo.x+o.hi.x)*.5f,(o.lo.y+o.hi.y)*.5f,(o.lo.z+o.hi.z)*.5f};
    fprintf(stdout,"[asset] scene %s: %llu verts, %llu tris, %llu uvs\n",path,(unsigned long long)o.nv,(unsigned long long)o.nt,(unsigned long long)o.nuv); return o;
}
static V3 sub(V3 a,V3 b){return(V3){a.x-b.x,a.y-b.y,a.z-b.z};}
static V3 cross(V3 a,V3 b){return(V3){a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
static V3 norm(V3 a){float n=sqrtf(a.x*a.x+a.y*a.y+a.z*a.z);if(n<1e-8f)return(V3){0,1,0};return(V3){a.x/n,a.y/n,a.z/n};}
static GLuint g_scene_texture=0, g_aya_texture=0, g_twisted_texture=0;
static float g_ge_bones[6][3][4];
static int g_ge_bone_count=0;
#define GE_TIMELINE_MAX_FRAMES 48
#define GE_TIMELINE_MAX_BONES 16
static float g_ge_timeline[GE_TIMELINE_MAX_FRAMES][GE_TIMELINE_MAX_BONES][3][4];
static int g_ge_timeline_frames=0, g_ge_timeline_bones=0;
static float g_aya_true_hand[GE_TIMELINE_MAX_FRAMES][3][4];
static float g_aya_true_hand_center[GE_TIMELINE_MAX_FRAMES][3];
static int g_aya_true_hand_frames=0;
/* Optional deterministic 4x sampling path. The source colors/UVs stay
   unchanged; only the texture storage resolution changes. Default remains
   the original-resolution atlas for regression parity. */
static int g_hd_sampling=0;
static const char *aya_material_path(void){return g_hd_sampling?"assets/materials/original_aya/aya_original_materials_hd_x4.txt":"assets/materials/original_aya/aya_original_materials.txt";}
static const char *weapon_material_path(void){return g_hd_sampling?"assets/materials/original_weapon/aya_original_weapon_materials_hd_x4.txt":"assets/materials/original_weapon/aya_original_weapon_materials.txt";}
/* Cross-validated against the same-frame PPSSPP GE draw trace.  The
   0x8b5e3a8 record is a command-state record (selector 0x102), not a bone
   matrix; the right-hand socket remains driven by this GE draw/palette. */
#define AYA_ARM_RIGHT_HAND_DRAW 1037
#define AYA_ARM_RIGHT_HAND_PALETTE_SLOT 12
#define AYA_ARM_RIGHT_HAND_TIMELINE_REGION 8
#define AYA_DRAW_RECORD_SELECTOR 0x102
#define AYA_BONE_PER_DRAW_CALLER 0x08b46e1c
#define AYA_BONE_BUILD_CALLER 0x08b4f6e8
#define AYA_TRUE_BONE_SLOT_WRITER 0x08b4f77c
#define AYA_TRUE_BONE_MATRIX_READ_ENTRY 0x08b52330
#define AYA_TRUE_BONE_MATRIX_COMMIT 0x08b5251c
#define AYA_TRUE_BONE_FLAG_WRITER 0x08b52554
#define AYA_SOURCE_BONE_COUNT 44
static GLuint load_bmp_texture(const char *path);
static uint8_t *read_file(const char *path,size_t *size);
static uint32_t rd32(const uint8_t *p);
static uint16_t rd16(const uint8_t *p);
#include "aya_source_skin.h"
#include "original_actor_runtime.h"
#include "original_scene_runtime.h"
#include "original_scene_collision.h"
static void material_color(float l){glColor3f(l,l,l);}
static void draw_obj(const Obj *o,float floor_y){
    int textured=o->has_uv&&g_scene_texture; if(textured){glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,g_scene_texture);}else glDisable(GL_TEXTURE_2D);
    glPushMatrix(); glTranslatef(0,floor_y,0); glBegin(GL_TRIANGLES);
    for(size_t i=0;i<o->nt;i++){Tri q=o->t[i];V3 a=o->v[q.a],b=o->v[q.b],c=o->v[q.c];V3 n=norm(cross(sub(b,a),sub(c,a)));float l=.35f+.65f*fmaxf(0,n.y*.7f+n.z*.3f);float h=((a.y+b.y+c.y)/3-o->lo.y)/(o->hi.y-o->lo.y+1e-6f);if(textured)material_color(l);else glColor3f((.20f+.08f*h)*l,(.30f+.12f*h)*l,(.34f+.18f*h)*l);if(textured&&q.ua>=0&&q.ua<(int)o->nuv)glTexCoord2f(o->uv[q.ua].u,o->uv[q.ua].v);glVertex3f(a.x-o->center.x,a.y-o->center.y,a.z-o->center.z);if(textured&&q.ub>=0&&q.ub<(int)o->nuv)glTexCoord2f(o->uv[q.ub].u,o->uv[q.ub].v);glVertex3f(b.x-o->center.x,b.y-o->center.y,b.z-o->center.z);if(textured&&q.uc>=0&&q.uc<(int)o->nuv)glTexCoord2f(o->uv[q.uc].u,o->uv[q.uc].v);glVertex3f(c.x-o->center.x,c.y-o->center.y,c.z-o->center.z);}
    glEnd(); glPopMatrix(); if(textured)glDisable(GL_TEXTURE_2D);
}
static V3 aya_rig_vertex(V3 p,float t,float shot);
static void draw_obj_character(const Obj *o,float x,float z,float yaw,float pose_t,float shot_t){
    if(!o||!o->nv||!o->nt)return;
    float h=o->hi.y-o->lo.y; float scale=h>0?1.84f/h:1.0f;
    int textured=o->has_uv&&g_aya_texture; if(textured){glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,g_aya_texture);}else glDisable(GL_TEXTURE_2D);
    glPushMatrix(); glTranslatef(x,0,z); glRotatef(yaw*180.0f/(float)M_PI,0,1,0); glScalef(scale,scale,scale); glTranslatef(0,-o->lo.y,0); glBegin(GL_TRIANGLES);
    for(size_t i=0;i<o->nt;i++){Tri q=o->t[i];V3 a=aya_rig_vertex(o->v[q.a],pose_t,shot_t),b=aya_rig_vertex(o->v[q.b],pose_t,shot_t),c=aya_rig_vertex(o->v[q.c],pose_t,shot_t);V3 n=norm(cross(sub(b,a),sub(c,a)));float l=.4f+.6f*fmaxf(0,n.y*.7f+n.z*.3f);float hh=((a.y+b.y+c.y)/3-o->lo.y)/(h+1e-6f);if(textured)material_color(.65f+.35f*l);else glColor3f((.26f+.10f*hh)*l,(.30f+.12f*hh)*l,(.34f+.16f*hh)*l);if(textured&&q.ua>=0&&q.ua<(int)o->nuv)glTexCoord2f(o->uv[q.ua].u,o->uv[q.ua].v);glVertex3f(a.x,a.y,a.z);if(textured&&q.ub>=0&&q.ub<(int)o->nuv)glTexCoord2f(o->uv[q.ub].u,o->uv[q.ub].v);glVertex3f(b.x,b.y,b.z);if(textured&&q.uc>=0&&q.uc<(int)o->nuv)glTexCoord2f(o->uv[q.uc].u,o->uv[q.uc].v);glVertex3f(c.x,c.y,c.z);}
    glEnd(); glPopMatrix(); if(textured)glDisable(GL_TEXTURE_2D);
}
static V3 rot_y_pivot(V3 p,V3 pivot,float a){float s=sinf(a),c=cosf(a),x=p.x-pivot.x,z=p.z-pivot.z;return(V3){pivot.x+x*c+z*s,p.y,pivot.z-z*c+x*s};}
static V3 rot_z_pivot(V3 p,V3 pivot,float a){float s=sinf(a),c=cosf(a),x=p.x-pivot.x,y=p.y-pivot.y;return(V3){pivot.x+x*c-y*s,pivot.y+x*s+y*c,p.z};}
static const V3 AYA_WEAPON_GRIP={.090f,1.790f,.130f};
/* Refit against the recovered right-hand draw bbox center (x=1.04656) after
   removing the invalid idle bone4 fallback: weapon center x=0.7406 -> +0.306. */
static const V3 AYA_WEAPON_MOUNT_CORRECTION={1.048355f,.029960f,-.252845f};
/* PPSSPP hand-axis fit over the 24-shot-frame capture, including the runtime
   0.35 rigid blend: 155 degrees minimizes muzzle-vs-hand-axis error. */
static const float AYA_WEAPON_YAW_CORRECTION=2.705260341f;
static V3 weapon_calibrated_vertex(V3 p){return rot_y_pivot(p,AYA_WEAPON_GRIP,AYA_WEAPON_YAW_CORRECTION);}
static void sample_ge_region(int region,float t,float shot,float out[3][3]){
    static const int fallback_bone[11]={2,2,2,3,3,3,4,4,4,5,5}; int bone=region>=0&&region<11?fallback_bone[region]:-1;
    for(int r=0;r<3;r++)for(int c=0;c<3;c++)out[r][c]=(r==c)?1.0f:0.0f;
    if(bone>=0&&bone<g_ge_bone_count)for(int r=0;r<3;r++)for(int c=0;c<3;c++)out[r][c]=g_ge_bones[bone][r][c];
    if(region==AYA_ARM_RIGHT_HAND_TIMELINE_REGION&&g_aya_true_hand_frames>1&&shot>0){
        float ff=fmodf(t*30.0f,(float)g_aya_true_hand_frames);if(ff<0)ff+=g_aya_true_hand_frames;int f0=(int)ff,f1=(f0+1)%g_aya_true_hand_frames;float a=ff-(float)f0,tw=.65f;
        for(int r=0;r<3;r++)for(int c=0;c<3;c++){float q=g_aya_true_hand[f0][r][c]*(1.0f-a)+g_aya_true_hand[f1][r][c]*a;out[r][c]=out[r][c]*(1.0f-tw)+q*tw;}
        return;
    }
    if(region>=0&&region<g_ge_timeline_bones&&g_ge_timeline_frames>1&&shot>0){
        float ff=fmodf(t*30.0f,(float)g_ge_timeline_frames);if(ff<0)ff+=g_ge_timeline_frames;int f0=(int)ff,f1=(f0+1)%g_ge_timeline_frames;float a=ff-(float)f0,tw=.65f;
        for(int r=0;r<3;r++)for(int c=0;c<3;c++){float q=g_ge_timeline[f0][region][r][c]*(1.0f-a)+g_ge_timeline[f1][region][r][c]*a;out[r][c]=out[r][c]*(1.0f-tw)+q*tw;}
    }
}
static int sample_true_hand_pose(float t,float shot,float R[3][3],V3 *center){
    if(g_aya_true_hand_frames<=1)return 0;
    int f0=0,f1=0;float a=0.0f;
    if(shot>0){float ff=fmodf(t*30.0f,(float)g_aya_true_hand_frames);if(ff<0)ff+=g_aya_true_hand_frames;f0=(int)ff;f1=(f0+1)%g_aya_true_hand_frames;a=ff-(float)f0;}
    center->x=g_aya_true_hand_center[f0][0]*(1.0f-a)+g_aya_true_hand_center[f1][0]*a;
    center->y=g_aya_true_hand_center[f0][1]*(1.0f-a)+g_aya_true_hand_center[f1][1]*a;
    center->z=g_aya_true_hand_center[f0][2]*(1.0f-a)+g_aya_true_hand_center[f1][2]*a;
    for(int r=0;r<3;r++)for(int c=0;c<3;c++)R[r][c]=g_aya_true_hand[f0][r][c]*(1.0f-a)+g_aya_true_hand[f1][r][c]*a;
    return 1;
}
static V3 weapon_pose_vertex(V3 p,float t,float shot){
    if(g_aya_true_hand_frames>1){
        float R[3][3];V3 center;
        sample_true_hand_pose(t,shot,R,&center);
        V3 q={p.x-AYA_WEAPON_GRIP.x,p.y-AYA_WEAPON_GRIP.y,p.z-AYA_WEAPON_GRIP.z};V3 rr={R[0][0]*q.x+R[0][1]*q.y+R[0][2]*q.z,R[1][0]*q.x+R[1][1]*q.y+R[1][2]*q.z,R[2][0]*q.x+R[2][1]*q.y+R[2][2]*q.z};p=(V3){center.x+rr.x,center.y+rr.y,center.z+rr.z};float sway=shot>0?sinf(t*2.1f)*.018f:0.0f,aim=shot>0?-.11f:0.0f;return rot_z_pivot(p,center,aim+sway);
    }
    p=weapon_calibrated_vertex(p); float gm[3][3];
    /* Idle uses the calibrated hand-local frame.  The old static GE fallback
       (bone4) is a spine/limb capture and puts the weapon below Aya's hand.
       During shooting, sample_ge_region switches to the source-record index
       36 timeline, so the weapon follows the recovered right-hand motion. */
    if(shot>0)sample_ge_region(AYA_ARM_RIGHT_HAND_TIMELINE_REGION,t,shot,gm);else for(int r=0;r<3;r++)for(int c=0;c<3;c++)gm[r][c]=(r==c)?1.0f:0.0f;
    V3 pivot={.95f,1.90f,0};V3 q={p.x-pivot.x,p.y-pivot.y,p.z-pivot.z};V3 r={gm[0][0]*q.x+gm[0][1]*q.y+gm[0][2]*q.z,gm[1][0]*q.x+gm[1][1]*q.y+gm[1][2]*q.z,gm[2][0]*q.x+gm[2][1]*q.y+gm[2][2]*q.z};float w=.35f;p=(V3){pivot.x+q.x*(1.0f-w)+r.x*w,pivot.y+q.y*(1.0f-w)+r.y*w,pivot.z+q.z*(1.0f-w)+r.z*w};float sway=sinf(t*2.1f)*.018f,aim=shot>0?-.11f:0.0f;p=rot_z_pivot(p,pivot,aim+sway);return (V3){p.x+AYA_WEAPON_MOUNT_CORRECTION.x,p.y+AYA_WEAPON_MOUNT_CORRECTION.y,p.z+AYA_WEAPON_MOUNT_CORRECTION.z};
}
static V3 aya_rig_vertex(V3 p,float t,float shot){
    float sway=sinf(t*2.1f)*.018f, aim=(shot>0?-.11f:0.0f), step=sinf(t*4.0f)*.035f;
    int region=-1; V3 pivot={0,1.70f,0};
    if(p.y>2.70f){region=2;pivot=(V3){0,2.83f,0};}
    else if(p.y>2.35f){region=1;pivot=(V3){0,2.30f,0};}
    else if(p.y>2.15f&&p.x>0.25f){region=6;pivot=(V3){.47f,2.29f,0};}
    else if(p.y>2.00f&&p.x>0.55f){region=7;pivot=(V3){.67f,2.17f,0};}
    else if(p.y>1.45f&&p.x>0.82f){region=8;pivot=(V3){.95f,1.90f,0};}
    else if(p.y>2.15f&&p.x<-.25f){region=3;pivot=(V3){-.47f,2.29f,0};}
    else if(p.y>2.00f&&p.x<-.55f){region=4;pivot=(V3){-.67f,2.17f,0};}
    else if(p.y>1.45f&&p.x<-.82f){region=5;pivot=(V3){-.95f,1.90f,0};}
    else if(p.y<1.35f){region=p.x>=0?10:9;pivot=(V3){p.x>=0?.12f:-.12f,1.29f,0};}
    else region=0;
    V3 true_hand_center={.95f,1.90f,0};
    if(region==AYA_ARM_RIGHT_HAND_TIMELINE_REGION&&g_aya_true_hand_frames>1){
        float gm[3][3];if(sample_true_hand_pose(t,shot,gm,&true_hand_center)){
            V3 q={p.x-true_hand_center.x,p.y-true_hand_center.y,p.z-true_hand_center.z};
            p=(V3){true_hand_center.x+gm[0][0]*q.x+gm[0][1]*q.y+gm[0][2]*q.z,true_hand_center.y+gm[1][0]*q.x+gm[1][1]*q.y+gm[1][2]*q.z,true_hand_center.z+gm[2][0]*q.x+gm[2][1]*q.y+gm[2][2]*q.z};
            pivot=true_hand_center;
        }
    }else if(region>=0&&g_ge_bone_count>0){float gm[3][3];sample_ge_region(region,t,shot,gm);float w=.35f;V3 q={p.x-pivot.x,p.y-pivot.y,p.z-pivot.z};V3 r={gm[0][0]*q.x+gm[0][1]*q.y+gm[0][2]*q.z,gm[1][0]*q.x+gm[1][1]*q.y+gm[1][2]*q.z,gm[2][0]*q.x+gm[2][1]*q.y+gm[2][2]*q.z};p=(V3){pivot.x+q.x*(1-w)+r.x*w,pivot.y+q.y*(1-w)+r.y*w,pivot.z+q.z*(1-w)+r.z*w};}
    if(region==2) p=rot_y_pivot(p,(V3){0,2.83f,0},sway);
    else if(region>=6&&region<=8) p=rot_z_pivot(p,pivot,aim+sway);
    else if(region>=3&&region<=5) p=rot_z_pivot(p,pivot,-aim-sway);
    else if(region==10) p=rot_z_pivot(p,pivot,step);
    else if(region==9) p=rot_z_pivot(p,pivot,-step);
    else p=rot_y_pivot(p,pivot,sway*.5f);
    return p;
}
static V3 actor_local_to_world(const Obj *aya,float x,float z,float yaw,V3 p){float h=aya->hi.y-aya->lo.y,scale=h>0?1.84f/h:1.0f;p.y-=aya->lo.y;p.x*=scale;p.y*=scale;p.z*=scale;float s=sinf(yaw),c=cosf(yaw);return(V3){x+p.x*c+p.z*s,p.y,z-p.x*s+p.z*c};}
/* Geometric barrel-tip estimate, measured from the real 243-vertex gun mesh.
   It is not yet a recovered original game muzzle socket. It shares the exact
   same recorded affine transform as the rendered weapon. */
static const V3 SOURCE_WEAPON_TIP={-.99990845f,0,.12123255f};
static V3 aya_muzzle_world(const Obj *aya,float x,float z,float yaw,float t,float shot){
    if(g_source_pair_ready){SourceSkin*weapon=source_active_weapon();return source_actor_world(weapon,x,z,yaw,source_skin_point(weapon,SOURCE_WEAPON_TIP,g_source_clip_t));}
    return actor_local_to_world(aya,x,z,yaw,weapon_pose_vertex((V3){.300f,1.795f,.106f},t,shot));
}
static V3 aya_muzzle_dir_world(const Obj *aya,float x,float z,float yaw,float t,float shot){
    V3 a=aya_muzzle_world(aya,x,z,yaw,t,shot),b;
    if(g_source_pair_ready){SourceSkin*weapon=source_active_weapon();V3 tip=SOURCE_WEAPON_TIP;tip.x-=.1f;b=source_actor_world(weapon,x,z,yaw,source_skin_point(weapon,tip,g_source_clip_t));}
    else b=actor_local_to_world(aya,x,z,yaw,weapon_pose_vertex((V3){.300f,1.795f,.306f},t,shot));
    return norm(sub(b,a));
}
static uint8_t *read_file(const char *path,size_t *size){FILE*f=fopen(path,"rb");if(!f)return NULL;fseek(f,0,SEEK_END);long n=ftell(f);fseek(f,0,SEEK_SET);uint8_t*d=(uint8_t*)malloc((size_t)n);if(!d||fread(d,1,(size_t)n,f)!=(size_t)n){free(d);fclose(f);return NULL;}fclose(f);*size=(size_t)n;return d;}
static uint16_t rd16(const uint8_t *p){return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t rd32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static GLuint load_bmp_texture(const char *path){
    size_t sz=0; uint8_t *d=read_file(path,&sz); if(!d||sz<54||d[0]!='B'||d[1]!='M'){fprintf(stderr,"[material] missing/invalid BMP %s\n",path);free(d);return 0;}
    uint32_t off=rd32(d+10),dib=rd32(d+14); int32_t w=(int32_t)rd32(d+18),h0=(int32_t)rd32(d+22); uint16_t planes=rd16(d+26),bpp=rd16(d+28); uint32_t comp=rd32(d+30);
    int rgba_masks=comp==3&&bpp==32&&dib>=108&&sz>=122&&rd32(d+54)==0x00ff0000&&rd32(d+58)==0x0000ff00&&rd32(d+62)==0x000000ff&&rd32(d+66)==0xff000000;
    if(dib<40||w<=0||w>16384||h0==0||h0==INT32_MIN||abs(h0)>16384||planes!=1||(bpp!=24&&bpp!=32)||(comp!=0&&!rgba_masks)){fprintf(stderr,"[material] unsupported BMP %s\n",path);free(d);return 0;}
    int topdown=h0<0, h=h0<0?-h0:h0; size_t row=((size_t)w*(bpp/8)+3)&~(size_t)3; if(off>sz||row*(size_t)h>sz-off){free(d);return 0;}size_t need=(size_t)w*(size_t)h*4; uint8_t *rgba=(uint8_t*)malloc(need); if(!rgba){free(d);return 0;}
    for(int y=0;y<h;y++){int sy=topdown?y:(h-1-y);const uint8_t *src=d+off+(size_t)sy*row;uint8_t *dst=rgba+(size_t)y*(size_t)w*4;for(int x=0;x<w;x++){dst[x*4+0]=src[x*(bpp/8)+2];dst[x*4+1]=src[x*(bpp/8)+1];dst[x*4+2]=src[x*(bpp/8)+0];dst[x*4+3]=bpp==32?src[x*4+3]:255;}}
    GLuint tex=0; glGenTextures(1,&tex); glBindTexture(GL_TEXTURE_2D,tex); glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR); glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR); glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT); glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT); glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,rgba); glBindTexture(GL_TEXTURE_2D,0); free(rgba); free(d); fprintf(stdout,"[material] %s: %dx%d BMP\n",path,w,h); return tex;
}
static int load_ge_bones(const char *path){size_t sz=0;uint8_t*d=read_file(path,&sz);if(!d)return 0;char*s=(char*)malloc(sz+1);if(!s){free(d);return 0;}memcpy(s,d,sz);s[sz]=0;char*p=s;int n=0;while(n<6&&(p=strstr(p,"\"matrix\""))){p=strchr(p,'[');if(!p)break;p++;for(int i=0;i<12;i++){while(*p&&!( (*p>='0'&&*p<='9')||*p=='-'||*p=='.'))p++;if(!*p)break;g_ge_bones[n][i/4][i%4]=strtof(p,&p);}n++;}free(s);free(d);if(n)fprintf(stdout,"[instrument] GE bone matrices %s: %d\n",path,n);return g_ge_bone_count=n;}
static int load_ge_timeline(const char *path){
    FILE*f=fopen(path,"rb");if(!f)return 0;char line[1024];int maxf=-1,maxb=-1,n=0;
    while(fgets(line,sizeof line,f)){
        if(line[0]=='f'||line[0]=='#')continue;
        char fs[32],bs[32];float v[12];
        int got=sscanf(line,"%31[^,],%31[^,],%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f,%f",fs,bs,&v[0],&v[1],&v[2],&v[3],&v[4],&v[5],&v[6],&v[7],&v[8],&v[9],&v[10],&v[11]);
        if(got!=14)continue;
        int fi=(int)strtol(fs,NULL,10),bi=-1;
        if(!strcmp(bs,"spine_lower"))bi=0;else if(!strcmp(bs,"spine_upper"))bi=1;else if(!strcmp(bs,"head"))bi=2;else if(!strcmp(bs,"arm_left_upper"))bi=3;else if(!strcmp(bs,"arm_left_forearm"))bi=4;else if(!strcmp(bs,"arm_left_hand"))bi=5;else if(!strcmp(bs,"arm_right_upper"))bi=6;else if(!strcmp(bs,"arm_right_forearm"))bi=7;else if(!strcmp(bs,"arm_right_hand"))bi=8;else if(!strcmp(bs,"leg_left"))bi=9;else if(!strcmp(bs,"leg_right"))bi=10;else if(!strcmp(bs,"spine"))bi=0;else if(!strcmp(bs,"arm_left"))bi=3;else if(!strcmp(bs,"arm_right"))bi=6;else if(!strcmp(bs,"legs"))bi=9;else bi=(int)strtol(bs,NULL,10);
        if(fi<0||fi>=GE_TIMELINE_MAX_FRAMES||bi<0||bi>=GE_TIMELINE_MAX_BONES)continue;
        float scale=0;for(int r=0;r<3;r++){float q=sqrtf(v[r*4]*v[r*4]+v[r*4+1]*v[r*4+1]+v[r*4+2]*v[r*4+2]);scale+=q;}scale/=3.0f;if(scale<1e-5f)scale=1.0f;
        for(int r=0;r<3;r++){for(int c=0;c<3;c++)g_ge_timeline[fi][bi][r][c]=v[r*4+c]/scale;g_ge_timeline[fi][bi][r][3]=0.0f;}
        if(fi>maxf)maxf=fi;
        if(bi>maxb)maxb=bi;
        n++;
    }
    fclose(f);g_ge_timeline_frames=maxf+1;g_ge_timeline_bones=maxb+1;if(n)fprintf(stdout,"[instrument] GE motion timeline %s: %d samples, %d frames x %d bones\n",path,n,g_ge_timeline_frames,g_ge_timeline_bones);return n;
}
static int load_true_right_hand_timeline(const char *path){
    FILE*f=fopen(path,"rb");if(!f)return 0;char line[4096];if(!fgets(line,sizeof line,f)){fclose(f);return 0;}int n=0,maxf=-1;
    while(fgets(line,sizeof line,f)){char*tok=strtok(line,",");if(!tok)continue;int fi=(int)strtol(tok,NULL,10);for(int k=0;k<3;k++)if(!(tok=strtok(NULL,",")))break;for(int k=0;k<3;k++){tok=strtok(NULL,",");if(!tok)break;g_aya_true_hand_center[fi][k]=strtof(tok,NULL);}float v[12];int ok=1;for(int i=0;i<12;i++){tok=strtok(NULL,",");if(!tok){ok=0;break;}v[i]=strtof(tok,NULL);}if(!ok||fi<0||fi>=GE_TIMELINE_MAX_FRAMES)continue;float s=0;for(int r=0;r<3;r++){float q=sqrtf(v[r*4]*v[r*4]+v[r*4+1]*v[r*4+1]+v[r*4+2]*v[r*4+2]);s+=q;}s/=3.0f;if(s<1e-5f)s=1.0f;for(int r=0;r<3;r++)for(int c=0;c<3;c++)g_aya_true_hand[fi][r][c]=v[r*4+c]/s;if(fi>maxf)maxf=fi;n++;}
    fclose(f);g_aya_true_hand_frames=maxf+1;if(n)fprintf(stdout,"[instrument] true Aya right-hand timeline %s: %d frames, source index 36\n",path,g_aya_true_hand_frames);return n;
}
static int load_draw_manifest(const char *path){size_t sz=0;uint8_t*d=read_file(path,&sz);if(!d)return 0;char*s=(char*)malloc(sz+1);if(!s){free(d);return 0;}memcpy(s,d,sz);s[sz]=0;int n=0;for(char*p=s;(p=strstr(p,"\"vtype\""));p+=8)n++;fprintf(stdout,"[material] draw manifest %s: %d records\n",path,n);free(s);free(d);return n;}
static Pmf load_pmf(const char *path){
    Pmf m;memset(&m,0,sizeof m);size_t sz=0;m.file=read_file(path,&sz);if(!m.file||sz<128||memcmp(m.file,"PMF1",4)){fprintf(stderr,"[asset] bad PMF %s\n",path);return m;}
    uint32_t h[6];memcpy(h,m.file+8,24);m.N=(int)h[1];m.M=(int)h[2];m.K=(int)h[3];m.nclip=(int)h[4];if(m.nclip>16)m.nclip=16;memcpy(m.scale,m.file+32,12);memcpy(m.off,m.file+44,12);uint32_t o[6];memcpy(o,m.file+64,24);m.kb=o[4];m.idx=(uint16_t*)(m.file+o[2]);m.keys=m.file+o[3];
    for(int i=0;i<m.nclip;i++){uint8_t*c=m.file+o[0]+i*32;memcpy(m.clips[i].name,c,15);memcpy(&m.clips[i].first,c+16,2);memcpy(&m.clips[i].count,c+18,2);memcpy(&m.clips[i].fps,c+20,4);memcpy(&m.clips[i].loop,c+24,2);}
    m.ok=1;fprintf(stdout,"[asset] model %s: %d verts, %d tris, %d keys\n",path,m.N,m.M/3,m.K);return m;
}
static void free_pmf(Pmf*m){free(m->file);memset(m,0,sizeof *m);}
static int clip_id(const Pmf*m,const char*n){for(int i=0;i<m->nclip;i++)if(!strcmp(m->clips[i].name,n))return i;return -1;}
static void clip_frame(const Pmf*m,int cid,float t,int*ka,int*kb,float*w){if(cid<0){*ka=*kb=0;*w=0;return;}const Clip*c=&m->clips[cid];float f=t*(c->fps>0?c->fps:10);if(f<0)f=0;int i=(int)f;*w=f-i;if(c->loop){i%=c->count;*ka=c->first+i;*kb=c->first+(i+1)%c->count;}else{if(i>=c->count-1){i=c->count-1;*w=0;}*ka=c->first+i;*kb=c->first+(i+1<c->count?i+1:i);}}
static void pmf_vertex(const Pmf*m,int frame,int id,V3*p,uint8_t*c){const uint8_t*r=m->keys+(size_t)frame*m->kb+(size_t)id*16;uint16_t u;int16_t x,y,z;memcpy(&u,r,2);(void)u;memcpy(c,r+4,4);memcpy(&x,r+8,2);memcpy(&y,r+10,2);memcpy(&z,r+12,2);p->x=(float)x/32768*m->scale[0]+m->off[0];p->y=(float)y/32768*m->scale[1]+m->off[1];p->z=(float)z/32768*m->scale[2]+m->off[2];}
static void draw_pmf(const Pmf*m,const char*clip,float t,float flash){if(!m->ok)return;int cid=clip_id(m,clip),a,b;float w;clip_frame(m,cid,t,&a,&b,&w);glBegin(GL_TRIANGLES);for(int i=0;i<m->M;i++){int id=m->idx[i];V3 p0,p1,p;uint8_t c0[4],c1[4];pmf_vertex(m,a,id,&p0,c0);pmf_vertex(m,b,id,&p1,c1);p.x=p0.x+(p1.x-p0.x)*w;p.y=p0.y+(p1.y-p0.y)*w;p.z=p0.z+(p1.z-p0.z)*w;float cr=((c0[0]+(c1[0]-c0[0])*w)/255.0f)*flash,cg=((c0[1]+(c1[1]-c0[1])*w)/255.0f)*flash,cb=((c0[2]+(c1[2]-c0[2])*w)/255.0f)*flash;glColor3f(cr,cg,cb);glVertex3f(p.x,p.y,p.z);}glEnd();}
static void draw_actor(const Pmf*m,const Actor*a,const char*normal,const char*hit,const char*dead){const char*clip=dead&&a->dead?dead:(a->hit_t>0?hit:normal);float flash=a->hit_t>0?1.5f:1.0f;glPushMatrix();glTranslatef(a->x,0,a->z);glRotatef(a->yaw*180.0f/(float)M_PI,0,1,0);draw_pmf(m,clip,a->anim_t,flash);glPopMatrix();}
static void line3(V3 a,V3 b,float r,float g,float bl){glColor3f(r,g,bl);glBegin(GL_LINES);glVertex3f(a.x,a.y,a.z);glVertex3f(b.x,b.y,b.z);glEnd();}
static void capture_frame_ppm(const char *path,int w,int h){
    size_t n=(size_t)w*(size_t)h*3;unsigned char*p=(unsigned char*)malloc(n);if(!p)return;
    glPixelStorei(GL_PACK_ALIGNMENT,1);glReadPixels(0,0,w,h,GL_RGB,GL_UNSIGNED_BYTE,p);FILE*f=fopen(path,"wb");
    if(f){fprintf(f,"P6\n%d %d\n255\n",w,h);for(int y=h-1;y>=0;y--)fwrite(p+(size_t)y*(size_t)w*3,1,(size_t)w*3,f);fclose(f);}free(p);
}
static void rect2(float x,float y,float w,float h,float r,float g,float b,float a){glColor4f(r,g,b,a);glBegin(GL_QUADS);glVertex2f(x,y);glVertex2f(x+w,y);glVertex2f(x+w,y+h);glVertex2f(x,y+h);glEnd();}
static void hud(int w,int h,const Actor*p,const Actor*e){glDisable(GL_DEPTH_TEST);glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();glOrtho(0,w,h,0,-1,1);glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();rect2(24,24,220,14,.08f,.08f,.10f,.85f);rect2(26,27,216*(p->hp/100.0f),8,.25f,.72f,.86f,1);rect2(w-264,24,240,14,.08f,.08f,.10f,.85f);rect2(w-262,27,236*(e->hp/100.0f),8,.86f,.25f,.22f,1);float cx=w*.5f,cy=h*.5f;glLineWidth(2);glColor3f(p->locked?1.0f:.78f,.62f,.20f);glBegin(GL_LINES);glVertex2f(cx-14,cy);glVertex2f(cx-4,cy);glVertex2f(cx+4,cy);glVertex2f(cx+14,cy);glVertex2f(cx,cy-14);glVertex2f(cx,cy-4);glVertex2f(cx,cy+4);glVertex2f(cx,cy+14);glEnd();if(p->locked&&!e->dead){glColor3f(1,.55f,.15f);glBegin(GL_LINE_LOOP);glVertex2f(cx-34,cy-34);glVertex2f(cx+34,cy-34);glVertex2f(cx+34,cy+34);glVertex2f(cx-34,cy+34);glEnd();}glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();glMatrixMode(GL_MODELVIEW);glEnable(GL_DEPTH_TEST);}
static void look_at(V3 cam,V3 target){
    V3 forward=norm(sub(target,cam)),right=norm(cross(forward,(V3){0,1,0})),up=cross(right,forward);
    GLfloat view[16]={right.x,up.x,-forward.x,0,right.y,up.y,-forward.y,0,right.z,up.z,-forward.z,0,0,0,0,1};
    glMultMatrixf(view);glTranslatef(-cam.x,-cam.y,-cam.z);
}
static void perspective(float fovy,float aspect,float zn,float zf){float t=tanf(fovy*.5f*(float)M_PI/180)*zn,r=t*aspect;glFrustum(-r,r,-t,t,zn,zf);}
typedef struct { float x0,z0,x1,z1; } CBox;
typedef struct { CBox boundary, boxes[32]; int n; } Collision;
static int load_collision(const char *path, Collision *c) {
    memset(c,0,sizeof *c); FILE *f=fopen(path,"rb"); if(!f){fprintf(stderr,"[collision] missing %s\n",path);return 0;}
    char line[256]; while(fgets(line,sizeof line,f)){ if(line[0]=='#')continue; char tag[16]; CBox b;
        if(sscanf(line,"%15s %f %f %f %f",tag,&b.x0,&b.z0,&b.x1,&b.z1)!=5)continue;
        if(!strcmp(tag,"boundary")){c->boundary=b;} else if(!strcmp(tag,"box")&&c->n<32){c->boxes[c->n++]=b;}
    } fclose(f); fprintf(stdout,"[collision] %s: %d boxes\n",path,c->n); return c->boundary.x1>c->boundary.x0;
}
static int blocked_point(const Collision *c,float x,float z,float r) {
    if(g_source_collision.enabled)return source_walk_blocked(x,z,r);
    if(x-r<c->boundary.x0||x+r>c->boundary.x1||z-r<c->boundary.z0||z+r>c->boundary.z1)return 1;
    for(int i=0;i<c->n;i++){const CBox*b=&c->boxes[i];if(x+r>b->x0&&x-r<b->x1&&z+r>b->z0&&z-r<b->z1)return 1;} return 0;
}
static void move_actor(const Collision*c,Actor*a,float dx,float dz,float r){float nx=a->x+dx,nz=a->z+dz;if(!blocked_point(c,nx,a->z,r))a->x=nx;if(!blocked_point(c,a->x,nz,r))a->z=nz;}
static int blocked_segment(const Collision*c,float ax,float az,float bx,float bz){float dx=bx-ax,dz=bz-az;if(g_source_collision.enabled){float length=sqrtf(dx*dx+dz*dz);return length>0&&source_static_ray((V3){ax,1.1f,az},(V3){dx/length,0,dz/length},length,NULL);}int n=(int)(sqrtf(dx*dx+dz*dz)/.04f)+1;for(int i=1;i<n;i++){float t=(float)i/(float)n;if(blocked_point(c,ax+dx*t,az+dz*t,.015f))return 1;}return 0;}
static int visible_target(const Collision*c,const Actor*p,const Actor*e){return !e->dead&&!blocked_segment(c,p->x,p->z,e->x,e->z);}
static int angle_target(const Actor*p,const Actor*e,float max_angle,float max_dist);
typedef struct { V3 origin,end; float distance; int valid,hit,blocked; } ShotTrace;
/* Existing M1 collision boxes are vertical columns. This is an exact slab
   intersection for those columns, not recovered original 3D level collision. */
static int ray_box_xz(const CBox*b,V3 o,V3 d,float max_t,float*enter,float*leave){
    double near_t=0,far_t=max_t;
    const double pos[2]={o.x,o.z},dir[2]={d.x,d.z},lo[2]={b->x0,b->z0},hi[2]={b->x1,b->z1};
    for(int i=0;i<2;i++){
        if(dir[i]==0){if(pos[i]<lo[i]||pos[i]>hi[i])return 0;continue;}
        double a=(lo[i]-pos[i])/dir[i],z=(hi[i]-pos[i])/dir[i];
        if(a>z){double temp=a;a=z;z=temp;}
        if(a>near_t)near_t=a;
        if(z<far_t)far_t=z;
        if(near_t>far_t)return 0;
    }
    *enter=(float)near_t;*leave=(float)far_t;return 1;
}
static ShotTrace trace_scene_shot(const Collision*c,V3 o,V3 d,const Actor*e,float range){
    ShotTrace r={.origin=o,.end=o};
    float length2=d.x*d.x+d.y*d.y+d.z*d.z;
    if(!isfinite(o.x)||!isfinite(o.y)||!isfinite(o.z)||!isfinite(length2)||fabsf(length2-1)>1e-4f||!isfinite(range)||range<=0)return r;
    r.valid=1;r.distance=range;
    float target_t=range,wall_t=range,enter,leave;int target_hit=0,wall_hit=0;
    if(!e->dead){
        if(g_original_actor_source.ok)target_hit=ray_original_actor(o,d,range,&target_t);
        else{
            /* Fallback adapter belongs only to guard.pmf; original source
               actors use their currently rendered triangle surfaces. */
            target_hit=combat_ray_vertical_capsule((CombatRay3){o.x,o.y,o.z},(CombatRay3){d.x,d.y,d.z},0,range,
                e->x+.20f*sinf(e->yaw),e->z+.20f*cosf(e->yaw),.30f,1.45f,.30f,&target_t);
        }
    }
    if(g_source_collision.enabled)wall_hit=source_static_ray(o,d,range,&wall_t);
    else{
        if(o.x<c->boundary.x0||o.x>c->boundary.x1||o.z<c->boundary.z0||o.z>c->boundary.z1){wall_t=0;wall_hit=1;}
        else if(ray_box_xz(&c->boundary,o,d,range,&enter,&leave)&&leave<range){wall_t=leave;wall_hit=1;}
        for(int i=0;i<c->n;i++)if(ray_box_xz(&c->boxes[i],o,d,range,&enter,&leave)&&enter<=wall_t){wall_t=enter;wall_hit=1;}
    }
    /* An occluder wins an exact tie; no angle cone or player-origin fallback. */
    if(wall_hit&&(!target_hit||wall_t<=target_t)){r.blocked=1;r.distance=wall_t;}
    else if(target_hit){r.hit=1;r.distance=target_t;}
    r.end=(V3){o.x+d.x*r.distance,o.y+d.y*r.distance,o.z+d.z*r.distance};return r;
}
static int check_source_spawn_collision(const Actor*player,const Actor*enemy){
    int checks=0,failures=0;float hit_t=0;
#define SOURCE_CHECK(expr) do{checks++;if(!(expr)){failures++;fprintf(stderr,"source collision check line %d failed\n",__LINE__);}}while(0)
    SOURCE_CHECK(g_source_collision.enabled&&g_source_collision.solid_materials==63&&g_source_collision.triangles==8551);
    SOURCE_CHECK(source_floor_at(player->x,player->z));SOURCE_CHECK(source_floor_at(enemy->x,enemy->z));
    int player_free=!source_walk_blocked(player->x,player->z,.22f),enemy_free=!source_walk_blocked(enemy->x,enemy->z,.22f);
    SOURCE_CHECK(player_free);SOURCE_CHECK(enemy_free);
    V3 o={player->x,1.4f,player->z},delta={enemy->x-player->x,0,enemy->z-player->z};float distance=sqrtf(delta.x*delta.x+delta.z*delta.z);V3 direction=norm(delta);
    int los_clear=!source_static_ray(o,direction,distance,&hit_t);SOURCE_CHECK(los_clear);
    /* Deliberately poison the legacy boundary and put a legacy column at the
       origin. These must have NO effect on the source adapter's shot or walk. */
    Collision poison={.boundary={-.001f,-.001f,.001f,.001f},.boxes={{-100,-100,100,100}},.n=1};
    Actor dead=*enemy;dead.dead=1;ShotTrace trace=trace_scene_shot(&poison,o,direction,&dead,distance);
    int legacy_ignored=trace.valid&&!trace.blocked;SOURCE_CHECK(legacy_ignored);
    SOURCE_CHECK(!blocked_point(&poison,player->x,player->z,.22f));SOURCE_CHECK(visible_target(&poison,player,enemy));
    SOURCE_CHECK(source_static_ray((V3){player->x,1,player->z},(V3){0,-1,0},2,&hit_t)&&hit_t>.95f&&hit_t<1.05f);
    SOURCE_CHECK(source_walk_blocked(100000,100000,.22f));
    int wall_probe=0;for(uint32_t i=0;i<g_source_collision.triangles&&!wall_probe;i++){
        SourceSolidTriangle*t=&g_source_collision.triangle[i];if(t->floor)continue;uint32_t v=t->vertex;
        V3 a=g_original_scene.v[v].p,b=g_original_scene.v[v+1].p,c=g_original_scene.v[v+2].p,n=cross(sub(b,a),sub(c,a));
        if(n.x*n.x+n.y*n.y+n.z*n.z<1e-10f)continue;
        n=norm(n);
        V3 midpoint={(a.x+b.x+c.x)/3,(a.y+b.y+c.y)/3,(a.z+b.z+c.z)/3};
        V3 start={midpoint.x+n.x*.1f,midpoint.y+n.y*.1f,midpoint.z+n.z*.1f};
        wall_probe=source_static_ray(start,(V3){-n.x,-n.y,-n.z},.2f,&hit_t);
    }SOURCE_CHECK(wall_probe);
    int wall_capsule_probe=0;float wall_x=0,wall_z=0;
    for(uint32_t i=0;i<g_source_collision.triangles&&!wall_capsule_probe;i++){
        SourceSolidTriangle*t=&g_source_collision.triangle[i];if(t->floor||t->lo.y>1||t->hi.y<1)continue;uint32_t v=t->vertex;
        V3 points[3]={g_original_scene.v[v].p,g_original_scene.v[v+1].p,g_original_scene.v[v+2].p};
        V3 n=cross(sub(points[1],points[0]),sub(points[2],points[0]));float horizontal=sqrtf(n.x*n.x+n.z*n.z);if(horizontal<1e-6f)continue;
        V3 intersections[3];int count=0;
        for(int edge=0;edge<3;edge++){V3 a=points[edge],b=points[(edge+1)%3];if(a.y==b.y||(a.y<1&&b.y<1)||(a.y>1&&b.y>1))continue;float u=(1-a.y)/(b.y-a.y);intersections[count++]=(V3){a.x+(b.x-a.x)*u,1,a.z+(b.z-a.z)*u};}
        if(count<2)continue;
        for(int sign=-1;sign<=1&&!wall_capsule_probe;sign+=2){wall_x=(intersections[0].x+intersections[1].x)*.5f+sign*n.x/horizontal*.11f;wall_z=(intersections[0].z+intersections[1].z)*.5f+sign*n.z/horizontal*.11f;
            if(!source_floor_disc_supported(wall_x,wall_z,.22f))continue;
            unsigned before=g_source_collision.movement_wall_blocked;wall_capsule_probe=source_walk_blocked(wall_x,wall_z,.22f)&&g_source_collision.movement_wall_blocked>before;
        }
    }SOURCE_CHECK(wall_capsule_probe);
    FILE*f=fopen("build/m1_source_collision_checks.txt","wb");if(f){fprintf(f,"source_collision_checks=%d\nsource_collision_failures=%d\nsource_spawn_player_capsule_free=%d\nsource_spawn_enemy_capsule_free=%d\nsource_spawn_los_clear=%d\nlegacy_collision_poison_ignored=%d\nsource_actual_wall_capsule_blocked=%d\nsource_actual_wall_probe_xz=%.9g,%.9g\n",checks,failures,player_free,enemy_free,los_clear,legacy_ignored,wall_capsule_probe,wall_x,wall_z);write_source_collision_result(f);fclose(f);}
#undef SOURCE_CHECK
    return failures?2:0;
}
static int check_scene_shots(void){
    Collision c={.boundary={-10,-10,10,10}};Actor e={.x=0,.z=3};int checks=0,failures=0;ShotTrace r;
#define SHOT_CHECK(expr) do{checks++;if(!(expr)){failures++;fprintf(stderr,"shot check line %d failed\n",__LINE__);}}while(0)
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(r.hit&&!r.blocked&&fabsf(r.distance-2.9f)<1e-5f);
    r=trace_scene_shot(&c,(V3){.7f,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(!r.hit&&!r.blocked);
    r=trace_scene_shot(&c,(V3){0,2,0},(V3){0,0,1},&e,9);SHOT_CHECK(!r.hit);
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,-1},&e,9);SHOT_CHECK(!r.hit);
    c.boxes[c.n++]=(CBox){-.4f,1,.4f,1.2f};
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(r.blocked&&!r.hit&&fabsf(r.distance-1)<1e-6f);
    r=trace_scene_shot(&c,(V3){0,1,1.1f},(V3){0,0,1},&e,9);SHOT_CHECK(r.blocked&&!r.hit&&r.distance==0);
    r=trace_scene_shot(&c,(V3){.7f,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(!r.hit&&!r.blocked);
    c.n=0;c.boundary.z1=2;
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(r.blocked&&!r.hit&&r.distance==2);
    c.boundary.z1=10;e.yaw=(float)M_PI;
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(r.hit&&fabsf(r.distance-2.5f)<1e-5f);
    e.dead=1;r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,1},&e,9);SHOT_CHECK(!r.hit);
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){0,0,2},&e,9);SHOT_CHECK(!r.valid);
    r=trace_scene_shot(&c,(V3){0,1,0},(V3){NAN,0,1},&e,9);SHOT_CHECK(!r.valid);
#undef SHOT_CHECK
    printf("scene shot checks=%d failures=%d\n",checks,failures);return failures?2:0;
}
static int angle_target(const Actor*p,const Actor*e,float max_angle,float max_dist){float dx=e->x-p->x,dz=e->z-p->z,d=sqrtf(dx*dx+dz*dz);if(d>max_dist||d<.05f)return 0;float fx=sinf(p->yaw),fz=cosf(p->yaw);float dot=(dx*fx+dz*fz)/d;return dot>=cosf(max_angle);}
static int check_source_clip_assets(void){
    /* Asset and state-machine checks only: no enemies, simulated shots, or
       claim that an input capture has been visually identified as an action. */
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_TIMER)<0)die(SDL_GetError());
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,2);SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,1);
    SDL_Window*window=SDL_CreateWindow("Source clip asset check",0,0,64,64,SDL_WINDOW_OPENGL|SDL_WINDOW_HIDDEN);
    if(!window)die(SDL_GetError());
    SDL_GLContext context=SDL_GL_CreateContext(window);if(!context)die(SDL_GetError());
    load_source_skin(&g_aya_source,"assets/models/aya_source_skin.bin",aya_material_path());
    load_source_skin(&g_weapon_source,"assets/models/aya_source_weapon.bin",weapon_material_path());
    load_source_clips("assets/models/aya_source_clips.txt");
    int transition_failures=0,clamp_failures=0;
    const int requested[8]={SOURCE_AIM,SOURCE_FIRE,SOURCE_AIM,SOURCE_REFERENCE,SOURCE_MOVE,SOURCE_APPROACH_FIRE,SOURCE_FIRE,SOURCE_REFERENCE};
    if(g_source_pair_ready)for(int i=0;i<8;i++){
        int before=g_source_active,expected=requested[i];
        if(!source_clip_available(expected))expected=expected==SOURCE_FIRE&&source_clip_available(SOURCE_AIM)?SOURCE_AIM:(expected==SOURCE_APPROACH_FIRE&&source_clip_available(SOURCE_FIRE)?SOURCE_FIRE:SOURCE_REFERENCE);
        update_source_clip(.025f,requested[i]==SOURCE_AIM,requested[i]==SOURCE_FIRE||requested[i]==SOURCE_APPROACH_FIRE,requested[i]==SOURCE_MOVE||requested[i]==SOURCE_APPROACH_FIRE);
        if(g_source_active!=expected||(before!=expected&&g_source_clip_t!=0))transition_failures++;
        update_source_clip(source_active_body()->duration+1,requested[i]==SOURCE_AIM,requested[i]==SOURCE_FIRE||requested[i]==SOURCE_APPROACH_FIRE,requested[i]==SOURCE_MOVE||requested[i]==SOURCE_APPROACH_FIRE);
        if(g_source_clip_t!=source_active_body()->duration)clamp_failures++;
    }
    FILE*f=fopen("build/m1_source_clip_check.txt","wb");
    if(f){write_source_clip_result(f);fprintf(f,"check_scope=asset_loading_and_state_machine_only\nsource_clip_transition_checks=%d\nsource_clip_transition_failures=%d\nsource_clip_clamp_checks=%d\nsource_clip_clamp_failures=%d\n",g_source_pair_ready?8:0,transition_failures,g_source_pair_ready?8:0,clamp_failures);fclose(f);}
    int valid=g_source_pair_ready&&!g_source_manifest_rejected&&!transition_failures&&!clamp_failures&&!g_source_pair_sync_failures;
    free_source_clips();free_source_skin(&g_aya_source);free_source_skin(&g_weapon_source);SDL_GL_DeleteContext(context);SDL_DestroyWindow(window);SDL_Quit();
    return valid?0:2;
}
static int has_option(int argc,char**argv,const char*option){for(int i=1;i<argc;i++)if(!strcmp(argv[i],option))return 1;return 0;}
static void write_test_scope(FILE*f,const char*mode,const Actor*player,const Actor*enemy,int source_spawn){
    fprintf(f,"test_mode_name=%s\ninitial_player_xz=%.9g,%.9g\ninitial_enemy_xz=%.9g,%.9g\ninitial_player_yaw=%.9g\ninitial_enemy_yaw=%.9g\noriginal_scene_spawn_selected=%d\n",mode,player->x,player->z,enemy->x,enemy->z,player->yaw,enemy->yaw,source_spawn);
    fprintf(f,"source_spawn_selected=%d\n",source_spawn);
}
int main(int argc,char**argv){
    g_hd_sampling=has_option(argc,argv,"--hd-sampling");
    if(argc>1&&!strcmp(argv[1],"--test-combat-rays"))return check_scene_shots();
    if(argc>1&&!strcmp(argv[1],"--test-source-clips"))return check_source_clip_assets();
    const char*scene=argc>1&&argv[1][0]!='-'?argv[1]:"assets\\scene\\nyc_block_uv.obj";
    const char*aya_path="assets\\models\\aya.pmf"; const char*guard_path="assets\\models\\guard.pmf"; const char*collision_path="assets\\scene\\nyc_block.col.txt";
    int capture_mode=argc>2&&!strcmp(argv[2],"--inspect-capture");
    if(capture_mode&&argc<4)die("--inspect-capture requires a separate source clip manifest");
    int inspect_mode=has_option(argc,argv,"--inspect-aya")||capture_mode;
    int preview_mode=has_option(argc,argv,"--preview")||inspect_mode;
    int ranged_test=has_option(argc,argv,"--test-ranged");
    int approach_fire_test=has_option(argc,argv,"--test-approach-fire");
    int held_close_test=has_option(argc,argv,"--test-held-close");
    int original_scene_test=has_option(argc,argv,"--test-original-scene");
    int source_spawn_test=has_option(argc,argv,"--test-source-spawn");
    int legacy_collision=has_option(argc,argv,"--legacy-collision");
    int legacy_scene=has_option(argc,argv,"--legacy-scene"),original_spawn=has_option(argc,argv,"--original-spawn");
    int test_mode=has_option(argc,argv,"--test")||preview_mode||ranged_test||held_close_test||original_scene_test||source_spawn_test||approach_fire_test;
    const char*test_mode_name=approach_fire_test?"approach_fire":(source_spawn_test?"source_spawn":(original_scene_test?"original_scene":(capture_mode?"capture":(ranged_test?"ranged":(held_close_test?"held_close":(preview_mode?"preview":"normal"))))));
    if(original_scene_test&&legacy_scene)die("--test-original-scene requires the original scene renderer");
    if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_TIMER)<0) die(SDL_GetError());
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,2); SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,1);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER,1); SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE,24);
    SDL_Window*win=SDL_CreateWindow("The 3rd Birthday HD Remaster - M1",SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,1920,1080,SDL_WINDOW_OPENGL|SDL_WINDOW_RESIZABLE);
    if(!win) die(SDL_GetError());
    SDL_GLContext ctx=SDL_GL_CreateContext(win); if(!ctx) die(SDL_GetError()); SDL_GL_SetSwapInterval(1);
    Obj obj={0}; Obj aya_original={0}; Obj aya_weapon={0}; Pmf aya={0}, guard={0}; Collision col; load_collision(collision_path,&col);
    if(!legacy_scene)load_original_scene();
    if(original_scene_test&&!g_original_scene.ok)die("original street asset check failed");
    if(g_original_scene.ok&&!legacy_collision&&!load_source_collision())die("original visible-static collision material proof failed");
    if(source_spawn_test&&!g_source_collision.enabled)die("--test-source-spawn requires original scene geometry collision");
    if(!g_original_scene.ok){obj=load_obj(scene);g_scene_texture=load_bmp_texture("assets/materials/scene_albedo.bmp");}
    int aya_draw_materials=0;
    load_source_skin(&g_aya_source,"assets/models/aya_source_skin.bin",aya_material_path());
    load_source_skin(&g_weapon_source,"assets/models/aya_source_weapon.bin",weapon_material_path());
    load_source_clips(capture_mode?argv[3]:"assets/models/aya_source_clips.txt");
    load_original_actor();
    if(!g_original_actor_source.ok){guard=load_pmf(guard_path);g_twisted_texture=load_bmp_texture("assets/materials/twisted_albedo.bmp");}
    if(capture_mode&&!source_clip_available(SOURCE_FIRE))die("inspection capture fire pair did not load");
    /* The recovered right-hand timeline is always loaded for provenance. It
       is only applied by the legacy GE fallback; the verified source-pair
       path owns its recorded body/weapon transforms and must not be blended
       with a different capture. */
    load_true_right_hand_timeline("assets/models/aya_true_right_hand_timeline.csv");
    if(!g_source_pair_ready){aya_original=load_obj("assets/models/aya_original_runtime.obj");aya=load_pmf(aya_path);g_aya_texture=load_bmp_texture("assets/materials/aya_albedo.bmp");aya_draw_materials=load_draw_manifest("assets/materials/aya_draw_materials.json");load_ge_bones("assets/models/aya_ge_matrices.json");load_ge_timeline("assets/models/aya_ge_hierarchy_timeline.csv");}
    if(test_mode){
        write_original_scene_probe();
        write_source_collision_probe();
        write_source_skin_probe_mode(&g_original_actor_source,"build/original_actor_cpu_probe.csv",1);
        write_source_skin_probe(&g_aya_source,"build/aya_source_cpu_probe.csv");write_source_skin_probe(&g_weapon_source,"build/aya_weapon_cpu_probe.csv");
        for(int i=0;i<SOURCE_CLIP_COUNT;i++)if(g_source_clips[i].loaded){
            char path[128];snprintf(path,sizeof path,"build/aya_%s_cpu_probe.csv",source_clip_labels[i]);write_source_skin_probe_mode(&g_source_clips[i].body,path,capture_mode);
            snprintf(path,sizeof path,"build/weapon_%s_cpu_probe.csv",source_clip_labels[i]);write_source_skin_probe_mode(&g_source_clips[i].weapon,path,capture_mode);
        }
    }
    Actor player={.x=0,.z=-.55f,.yaw=0,.hp=100}, enemy={.x=1.30f,.z=0.0f,.yaw=(float)M_PI,.hp=100};
    if(capture_mode)player.z=0;
    if(ranged_test){player.x=-1.25f;enemy.z=-.55f;}
    int source_spawn_selected=g_original_scene.ok&&(original_spawn||!test_mode||source_spawn_test);
    if(source_spawn_selected){player.x=g_original_scene.player[0];player.z=g_original_scene.player[1];player.yaw=g_original_scene.player[2];enemy.x=g_original_scene.enemy[0];enemy.z=g_original_scene.enemy[1];enemy.yaw=g_original_scene.enemy[2];}
    const Actor initial_player=player,initial_enemy=enemy;
    int source_spawn_check_failed=source_spawn_test&&check_source_spawn_collision(&player,&enemy);
    int run=1, prev_r=0, prev_f=0, ge_started=0, test_frames=0, od_phase=0, od_seen=0, od_return=0, shots_hit=0;
    float od_t=0, shot_flash=0; ShotTrace last_shot={0};int ray_shots=0,ray_blocked=0,ray_misses=0;
    FILE*shot_log=test_mode?fopen("build/m1_shot_rays.csv","wb"):NULL;
    if(shot_log)fprintf(shot_log,"frame,clip,time,ox,oy,oz,dx,dy,dz,ex,ez,hit,blocked,distance,enemy_source_time,enemy_yaw,scene_collision,range,collision_adapter\n");
    Uint64 prev=SDL_GetPerformanceCounter(); if(test_mode&&!inspect_mode&&!original_scene_test) player.locked=1;
    glEnable(GL_DEPTH_TEST); glDisable(GL_CULL_FACE); glEnable(GL_FOG);
    { GLfloat c[4]={.025f,.045f,.055f,1}; glFogfv(GL_FOG_COLOR,c); glFogi(GL_FOG_MODE,GL_LINEAR); glFogf(GL_FOG_START,6); glFogf(GL_FOG_END,18); }
    while(run){
        Uint64 now=SDL_GetPerformanceCounter(); float dt=(float)((now-prev)/(double)SDL_GetPerformanceFrequency()); prev=now;
        if(dt>.1f) dt=.1f;
        test_frames++;
        SDL_Event ev; int fire=0; while(SDL_PollEvent(&ev)){ if(ev.type==SDL_QUIT) run=0; if(ev.type==SDL_KEYDOWN&&!ev.key.repeat){ if(ev.key.keysym.sym==SDLK_ESCAPE)run=0; if(ev.key.keysym.sym==SDLK_SPACE)fire=1; } }
        if(test_mode&&!inspect_mode&&!original_scene_test&&test_frames%36==0) fire=1;
        if((ranged_test||held_close_test||source_spawn_test)&&test_frames>=144)fire=1;
        if(approach_fire_test&&test_frames>=36)fire=1;
        const Uint8*k=SDL_GetKeyboardState(NULL); int rnow=k[SDL_SCANCODE_R]?1:0; int fnow=k[SDL_SCANCODE_F]?1:0;
        if(k[SDL_SCANCODE_SPACE])fire=1;
        if(test_mode&&!preview_mode&&!original_scene_test&&test_frames==12) fnow=1;
        float sim_dt=od_phase?dt*.25f:dt;
        if(!od_phase){
            if(k[SDL_SCANCODE_A]) player.yaw-=1.8f*sim_dt;
            if(k[SDL_SCANCODE_D]) player.yaw+=1.8f*sim_dt;
            float fx=sinf(player.yaw), fz=cosf(player.yaw);
            if(k[SDL_SCANCODE_W]||approach_fire_test) move_actor(&col,&player,fx*1.6f*sim_dt,fz*1.6f*sim_dt,.22f);
            if(k[SDL_SCANCODE_S]) move_actor(&col,&player,-fx*1.0f*sim_dt,-fz*1.0f*sim_dt,.22f);
        }
        if(rnow&&!prev_r){
            if(!enemy.dead&&angle_target(&player,&enemy,1.05f,8.0f)&&visible_target(&col,&player,&enemy)) player.locked=!player.locked; else player.locked=0;
        }
        prev_r=rnow;
        if(player.locked&&!enemy.dead){float dx=enemy.x-player.x,dz=enemy.z-player.z;player.yaw=atan2f(dx,dz);if(!visible_target(&col,&player,&enemy))player.locked=0;}
        if(fnow&&!prev_f&&player.locked&&!enemy.dead&&od_phase==0){od_phase=1;od_t=0;od_seen=1;} prev_f=fnow;
        if(od_phase){od_t+=dt;if(od_phase==1&&od_t>.32f){od_phase=2;od_t=0;}else if(od_phase==2&&od_t>1.0f){od_phase=3;od_t=0;}else if(od_phase==3&&od_t>.32f){od_phase=0;od_t=0;od_return=1;}}
        if(!enemy.dead&&!od_phase&&!original_scene_test){float dx=player.x-enemy.x,dz=player.z-enemy.z,d=sqrtf(dx*dx+dz*dz);if(d>1.35f&&!ranged_test)move_actor(&col,&enemy,dx/d*.55f*sim_dt,dz/d*.55f*sim_dt,.22f);enemy.yaw=atan2f(player.x-enemy.x,player.z-enemy.z);}
        if(player.fire_cd>0)player.fire_cd-=sim_dt;
        if(player.shoot_t>0)player.shoot_t-=sim_dt;
        if(player.hit_t>0)player.hit_t-=sim_dt;
        if(enemy.hit_t>0)enemy.hit_t-=sim_dt;
        if(shot_flash>0)shot_flash-=sim_dt;
        player.anim_t+=sim_dt; player.ge_t+=sim_dt; enemy.anim_t+=sim_dt;
        pose_original_actor(&enemy,sim_dt);
        int shot_requested=fire&&!enemy.dead&&player.fire_cd<=0&&od_phase==0;
        if(shot_requested){player.fire_cd=.32f;player.anim_t=0;player.shoot_t=.18f;shot_flash=.12f;}
        update_source_clip(sim_dt,player.locked,capture_mode||player.shoot_t>0||(!enemy.dead&&!od_phase&&(k[SDL_SCANCODE_SPACE]||((ranged_test||held_close_test||source_spawn_test)&&test_frames>=144)||approach_fire_test)),!od_phase&&(k[SDL_SCANCODE_W]||k[SDL_SCANCODE_S]||approach_fire_test));
        if(capture_mode){SourceSkin*s=source_active_body();unsigned sample=(unsigned)(test_frames-1);if(sample>=s->frames)sample=s->frames-1;g_source_clip_t=s->time[sample];}
        if(shot_requested){
            if(!ge_started){player.ge_t=0;ge_started=1;}
            V3 origin=aya_muzzle_world(&aya_original,player.x,player.z,player.yaw,player.ge_t,player.shoot_t);
            V3 direction=aya_muzzle_dir_world(&aya_original,player.x,player.z,player.yaw,player.ge_t,player.shoot_t);
            float shot_range=player.locked?9.0f:7.0f;
            last_shot=trace_scene_shot(&col,origin,direction,&enemy,shot_range);ray_shots++;
            ray_blocked+=last_shot.blocked;ray_misses+=!last_shot.hit&&!last_shot.blocked;
            if(shot_log)fprintf(shot_log,"%d,%s,%.8f,%.8f,%.8f,%.8f,%.8f,%.8f,%.8f,%.8f,%.8f,%d,%d,%.8f,%.9g,%.9g,%s,%.9g,%s\n",test_frames,source_clip_labels[g_source_active],g_source_clip_t,origin.x,origin.y,origin.z,direction.x,direction.y,direction.z,enemy.x,enemy.z,last_shot.hit,last_shot.blocked,last_shot.distance,g_original_actor_t,enemy.yaw,source_collision_name(),shot_range,source_collision_name());
            if(last_shot.hit){shots_hit++;enemy.hit_t=.28f;enemy.hp-=25;if(enemy.hp<=0){enemy.hp=0;enemy.dead=1;enemy.anim_t=0;player.locked=0;}}
        }
        int w,h; SDL_GetWindowSize(win,&w,&h); glViewport(0,0,w,h); glClearColor(.008f,.012f,.016f,1); glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        glMatrixMode(GL_PROJECTION); glLoadIdentity(); perspective(55,(float)w/(float)h,.03f,80); glMatrixMode(GL_MODELVIEW); glLoadIdentity();
        float fx=sinf(player.yaw),fz=cosf(player.yaw); V3 forward={fx,0,fz}, right={cosf(player.yaw),0,-sinf(player.yaw)};
        V3 normal_cam={player.x-forward.x*3.1f+right.x*.55f,1.55f,player.z-forward.z*3.1f+right.z*.55f};
        V3 normal_target={player.x+forward.x*1.8f,1.05f,player.z+forward.z*1.8f}; V3 cam=normal_cam,target=normal_target;
        if(od_phase){
            V3 dive_cam={enemy.x+.55f,1.15f,enemy.z-.65f},dive_target={enemy.x,1.0f,enemy.z};
            if(od_phase==1){float q=od_t/.32f;if(q>1)q=1;cam=(V3){normal_cam.x+(dive_cam.x-normal_cam.x)*q,normal_cam.y+(dive_cam.y-normal_cam.y)*q,normal_cam.z+(dive_cam.z-normal_cam.z)*q};target=(V3){normal_target.x+(dive_target.x-normal_target.x)*q,normal_target.y+(dive_target.y-normal_target.y)*q,normal_target.z+(dive_target.z-normal_target.z)*q};}
            else if(od_phase==2){cam=dive_cam;target=dive_target;}
            else{float q=od_t/.32f;if(q>1)q=1;cam=(V3){dive_cam.x+(normal_cam.x-dive_cam.x)*q,dive_cam.y+(normal_cam.y-dive_cam.y)*q,dive_cam.z+(normal_cam.z-dive_cam.z)*q};target=(V3){dive_target.x+(normal_target.x-dive_target.x)*q,dive_target.y+(normal_target.y-dive_target.y)*q,dive_target.z+(normal_target.z-dive_target.z)*q};}
        }
        if(player.locked&&!enemy.dead&&!od_phase) target=(V3){enemy.x,1.0f,enemy.z};
        if(preview_mode){cam=(V3){-2.40f,1.45f,-2.40f};target=(V3){.45f,1.15f,0.0f};}
        if(inspect_mode){cam=(V3){1.7f,1.35f,2.5f};target=(V3){0,.95f,-.4f};}
        if(capture_mode){cam=(V3){-2.4f,1.45f,1.4f};target=(V3){0,.95f,.2f};}
        look_at(cam,target);
        if(g_original_scene.ok)draw_original_scene();else{float floor_y=(obj.hi.y-obj.lo.y)*.5f;draw_obj(&obj,floor_y);}
        if(g_source_pair_ready){draw_source_skin(source_active_body(),player.x,player.z,player.yaw,g_source_clip_t);draw_source_skin(source_active_weapon(),player.x,player.z,player.yaw,g_source_clip_t);}
        else if(aya_original.nv){draw_obj_character(&aya_original,player.x,player.z,player.yaw,player.ge_t,player.shoot_t);/* Legacy "weapon" OBJ is Aya packet86, not a weapon. */}
        else draw_actor(&aya,&player,"idle","hurt","idle");
        if(!inspect_mode){if(g_original_actor_source.ok)draw_original_actor(&enemy);else draw_actor(&guard,&enemy,"walk","hit","dead");}
        if(shot_flash>0&&last_shot.valid){glLineWidth(3);line3(last_shot.origin,last_shot.end,1,.55f,.16f);} hud(w,h,&player,&enemy);
        if(preview_mode&&(test_frames==72||test_frames==108))capture_frame_ppm(inspect_mode?(test_frames==72?"build/m1_inspect_aya_a.ppm":"build/m1_inspect_aya_b.ppm"):(test_frames==72?"build/m1_preview_fire_a.ppm":"build/m1_preview_fire_b.ppm"),w,h);
        if(ranged_test&&(test_frames==180||test_frames==240))capture_frame_ppm(test_frames==180?"build/m1_original_enemy_ranged_a.ppm":"build/m1_original_enemy_ranged_b.ppm",w,h);
        if(original_scene_test&&(test_frames==30||test_frames==90))capture_frame_ppm(test_frames==30?"build/m1_original_scene_a.ppm":"build/m1_original_scene_b.ppm",w,h);
        if(source_spawn_test&&(test_frames==180||test_frames==240))capture_frame_ppm(test_frames==180?"build/m1_source_spawn_a.ppm":"build/m1_source_spawn_b.ppm",w,h);
        if(capture_mode&&((test_frames-1)%10==0||(unsigned)test_frames==source_active_body()->frames)){char path[128];snprintf(path,sizeof path,"build/m1_dense_frame_%03d.ppm",test_frames-1);capture_frame_ppm(path,w,h);}
        SDL_GL_SwapWindow(win);
        char title[240];snprintf(title,sizeof title,"The 3rd Birthday HD Remaster - M1 | Aya %u source bones, %u packets | %u tris | weapon %u tris | clip %s %.2fs | HP %.0f / E %.0f | %s",g_aya_source.bones,g_aya_source.packets,g_aya_source.vertices/3,g_weapon_source.vertices/3,source_clip_labels[g_source_active],g_source_clip_t,player.hp,enemy.hp,od_phase?"OVERDIVE":"R lock  SPACE fire");SDL_SetWindowTitle(win,title);
        if(test_mode&&test_frames>360)run=0;
        if(original_scene_test&&test_frames>=120)run=0;
        if(capture_mode&&(unsigned)test_frames>=source_active_body()->frames)run=0;
    }
    if(test_mode){FILE*f=fopen("build\\m1_test_result.txt","wb");if(f){int collision_ok=g_source_collision.enabled?-1:blocked_point(&col,col.boundary.x0-.1f,0,.22f);int los_blocked=g_source_collision.enabled?-1:blocked_segment(&col,0,0,0,.4f);V3 md=(g_source_pair_ready||aya_original.nv)?aya_muzzle_dir_world(&aya_original,player.x,player.z,player.yaw,player.ge_t,player.shoot_t):(V3){0,0,1};float muzzle_dir_norm=sqrtf(md.x*md.x+md.y*md.y+md.z*md.z);fprintf(f,"hd_sampling=%d\naya_tris=%d\naya_runtime_tris=%llu\nweapon_tris=%llu\naya_material_draws=%d\naya_ge_timeline_frames=%d\naya_ge_timeline_bones=%d\naya_true_hand_timeline_frames=%d\naya_true_hand_timeline_loaded=%d\naya_true_hand_timeline_used=%d\naya_true_hand_timeline_bound=%d\naya_true_right_hand_source_index=%d\naya_arm_right_hand_draw=%d\naya_arm_right_hand_palette_slot=%d\naya_arm_right_hand_timeline_region=%d\naya_bone_per_draw_caller=0x%x\naya_bone_build_caller=0x%x\naya_true_bone_slot_writer=0x%x\naya_true_bone_matrix_read_entry=0x%x\naya_true_bone_matrix_commit=0x%x\naya_true_bone_flag_writer=0x%x\naya_source_bone_count=%d\naya_draw_record_selector=0x%x\naya_draw_record_bound=0\nmuzzle_dir_norm=%.6f\ntwisted_tris=%d\nenemy_hp=%.0f\nenemy_dead=%d\nshots_hit=%d\ncollision_boundary=%d\nlos_blocked=%d\noverdive_seen=%d\noverdive_return=%d\n",g_hd_sampling,aya.M/3,(unsigned long long)(g_source_pair_ready?g_aya_source.vertices/3:aya_original.nt),(unsigned long long)(g_source_pair_ready?g_weapon_source.vertices/3:aya_weapon.nt),aya_draw_materials,g_ge_timeline_frames,g_ge_timeline_bones,g_aya_true_hand_frames,g_aya_true_hand_frames>0,(!g_source_pair_ready&&g_aya_true_hand_frames>1&&ge_started),(!g_source_pair_ready&&g_aya_true_hand_frames>1&&ge_started),g_source_pair_ready?-1:36,AYA_ARM_RIGHT_HAND_DRAW,AYA_ARM_RIGHT_HAND_PALETTE_SLOT,AYA_ARM_RIGHT_HAND_TIMELINE_REGION,AYA_BONE_PER_DRAW_CALLER,AYA_BONE_BUILD_CALLER,AYA_TRUE_BONE_SLOT_WRITER,AYA_TRUE_BONE_MATRIX_READ_ENTRY,AYA_TRUE_BONE_MATRIX_COMMIT,AYA_TRUE_BONE_FLAG_WRITER,AYA_SOURCE_BONE_COUNT,AYA_DRAW_RECORD_SELECTOR,muzzle_dir_norm,g_original_actor_source.ok?(int)(g_original_actor_source.vertices/3):guard.M/3,enemy.hp,enemy.dead,shots_hit,collision_ok,los_blocked,od_seen,od_return);write_test_scope(f,test_mode_name,&initial_player,&initial_enemy,source_spawn_selected);write_original_scene_result(f);write_source_collision_result(f);fclose(f);}}
    if(shot_log)fclose(shot_log);
    if(test_mode){FILE*f=fopen("build/m1_source_skin_result.txt","wb");if(f){fprintf(f,"muzzle_ray_shots=%d\nmuzzle_ray_hits=%d\nmuzzle_ray_blocked=%d\nmuzzle_ray_misses=%d\nangle_hit_fallback=0\nplayer_los_fallback=0\n",ray_shots,shots_hit,ray_blocked,ray_misses);fprintf(f,"aya_source_skin_loaded=%d\naya_source_bones=%u\naya_source_packets=%u\naya_source_vertices=%u\naya_source_samples=%u\naya_source_materials=%u\nweapon_source_loaded=%d\nweapon_source_vertices=%u\nweapon_source_samples=%u\nlegacy_weapon_enabled=0\n",g_aya_source.ok,g_aya_source.bones,g_aya_source.packets,g_aya_source.vertices,g_aya_source.frames,g_aya_source.materials,g_weapon_source.ok,g_weapon_source.vertices,g_weapon_source.frames);write_source_clip_result(f);write_original_actor_result(f);write_test_scope(f,test_mode_name,&initial_player,&initial_enemy,source_spawn_selected);write_original_scene_result(f);write_source_collision_result(f);fclose(f);}}
    if(test_mode){FILE*f=fopen("build/m1_original_scene_result.txt","wb");if(f){write_test_scope(f,test_mode_name,&initial_player,&initial_enemy,source_spawn_selected);write_original_scene_result(f);write_source_collision_result(f);fclose(f);}}
    int scene_check_failed=original_scene_test&&(!g_original_scene.ok||g_original_scene.probe_vertices!=g_original_scene.vertices||g_original_scene.vertex_hash!=g_original_scene.loaded_vertex_hash||g_original_scene.rendered_frames!=(unsigned)test_frames||g_original_scene.rendered_draws!=(unsigned)test_frames*g_original_scene.draws||g_original_scene.context_gl_errors);
    free_source_collision();free_original_scene();free_original_actor();free_source_clips();free_source_skin(&g_aya_source);free_source_skin(&g_weapon_source);free(obj.v);free(obj.uv);free(obj.t);free(aya_original.v);free(aya_original.uv);free(aya_original.t);free(aya_weapon.v);free(aya_weapon.uv);free(aya_weapon.t);if(g_scene_texture)glDeleteTextures(1,&g_scene_texture);if(g_aya_texture)glDeleteTextures(1,&g_aya_texture);if(g_twisted_texture)glDeleteTextures(1,&g_twisted_texture);free_pmf(&aya);free_pmf(&guard);SDL_GL_DeleteContext(ctx);SDL_DestroyWindow(win);SDL_Quit();return scene_check_failed||source_spawn_check_failed?2:0;
}
