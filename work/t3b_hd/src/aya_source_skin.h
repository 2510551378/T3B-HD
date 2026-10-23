/* Original packet/source-index skin replay. Included after the common asset IO.
   GE storage is column-major 3x4; the exporter explicitly converts it to rows.
   This path never uses the legacy region/pivot rig or discards translation. */
typedef struct { V3 p; V2 uv; V3 normal; uint32_t count, bone[8]; float weight[8]; } SourceVertex;
typedef struct { uint32_t first, count, material, primitive; } SourcePacket;
typedef struct { GLuint texture; int alpha_ref, blend, wrap_s, wrap_t; float su,sv,ou,ov; } SourceMaterial;
typedef struct {
    uint32_t bones, packets, vertices, frames, materials, flags;
    float units, floor, duration; int *parent; SourceVertex *v; SourcePacket *packet;
    float *time, *matrix; V3 *posed; SourceMaterial material[16]; int ok;
} SourceSkin;
static SourceSkin g_aya_source, g_weapon_source;
static float source_f32(const uint8_t *p){uint32_t bits=rd32(p);float f;memcpy(&f,&bits,4);return f;}
static void free_source_skin(SourceSkin*s){
    for(uint32_t i=0;i<s->materials&&i<16;i++)if(s->material[i].texture)glDeleteTextures(1,&s->material[i].texture);
    free(s->parent);free(s->v);free(s->packet);free(s->time);free(s->matrix);free(s->posed);memset(s,0,sizeof *s);
}
static int load_source_skin(SourceSkin*s,const char*path,const char*material_path){
    size_t size=0;uint8_t*d=read_file(path,&size);if(!d)return 0;
    if(size<56||memcmp(d,"T3BSKN2\0",8)||rd32(d+8)!=2){free(d);return 0;}
    memset(s,0,sizeof *s);s->bones=rd32(d+12);s->packets=rd32(d+16);s->vertices=rd32(d+20);s->frames=rd32(d+24);s->materials=rd32(d+28);s->flags=rd32(d+32);s->units=source_f32(d+44);s->floor=source_f32(d+48);
    if(!s->bones||s->bones>64||!s->packets||s->packets>4096||!s->vertices||s->vertices>100000||s->frames<2||s->frames>4096||!s->materials||s->materials>16||!(s->units>0)||!isfinite(s->units)||!isfinite(s->floor)){free(d);memset(s,0,sizeof *s);return 0;}
    size_t expected=56+(size_t)s->bones*4+(size_t)s->packets*16+(size_t)s->vertices*100+(size_t)s->frames*4+(size_t)s->frames*s->bones*48;
    if(size!=expected){fprintf(stderr,"[source-skin] invalid byte count %s\n",path);free(d);memset(s,0,sizeof *s);return 0;}
    s->parent=calloc(s->bones,sizeof *s->parent);s->v=calloc(s->vertices,sizeof *s->v);s->packet=calloc(s->packets,sizeof *s->packet);s->time=calloc(s->frames,sizeof *s->time);s->matrix=calloc((size_t)s->frames*s->bones*12,sizeof(float));s->posed=calloc(s->vertices,sizeof *s->posed);
    if(!s->parent||!s->v||!s->packet||!s->time||!s->matrix||!s->posed)die("source skin allocation failed");
    size_t p=56;int valid=1;
    for(uint32_t i=0;i<s->bones;i++,p+=4){s->parent[i]=(int32_t)rd32(d+p);if(s->parent[i]<-1||s->parent[i]>=(int)s->bones)valid=0;}
    for(uint32_t i=0;i<s->bones&&valid;i++){int j=(int)i;uint32_t depth=0;while(j>=0&&depth++<=s->bones)j=s->parent[j];if(depth>s->bones)valid=0;}
    uint32_t next=0;
    for(uint32_t i=0;i<s->packets;i++,p+=16){SourcePacket*q=&s->packet[i];q->first=rd32(d+p);q->count=rd32(d+p+4);q->material=rd32(d+p+8);q->primitive=rd32(d+p+12);if(q->first!=next||q->count>s->vertices-next||q->count%3||q->primitive!=3||q->material>=s->materials)valid=0;next+=q->count;}
    if(next!=s->vertices)valid=0;
    for(uint32_t i=0;i<s->vertices;i++,p+=100){
        SourceVertex*v=&s->v[i];float values[8];for(int k=0;k<8;k++){values[k]=source_f32(d+p+k*4);if(!isfinite(values[k]))valid=0;}v->p=(V3){values[0],values[1],values[2]};v->uv=(V2){values[3],values[4]};v->normal=(V3){values[5],values[6],values[7]};v->count=rd32(d+p+32);if(!v->count||v->count>8)valid=0;float sum=0;
        for(int k=0;k<8;k++){v->bone[k]=rd32(d+p+36+k*4);v->weight[k]=source_f32(d+p+68+k*4);if(k<(int)v->count){if(v->bone[k]>=s->bones||v->weight[k]<0||!isfinite(v->weight[k]))valid=0;sum+=v->weight[k];}}
        if(sum<.95f||sum>1.01f)valid=0;
    }
    for(uint32_t i=0;i<s->frames;i++,p+=4){s->time[i]=source_f32(d+p);if(!isfinite(s->time[i])||(i&&s->time[i]<=s->time[i-1]))valid=0;}
    for(size_t i=0;i<(size_t)s->frames*s->bones*12;i++,p+=4){s->matrix[i]=source_f32(d+p);if(!isfinite(s->matrix[i]))valid=0;}
    free(d);
    FILE*f=fopen(material_path,"rb");char tag[32];unsigned count=0;
    if(!f)valid=0;
    if(f){if(fscanf(f,"%31s %u",tag,&count)!=2||strcmp(tag,"T3BMAT1")||count!=s->materials)valid=0;
        for(uint32_t i=0;i<s->materials&&valid;i++){unsigned index;char texture[512];SourceMaterial*m=&s->material[i];
            if(fscanf(f,"%u %511s %d %d %f %f %f %f %d %d",&index,texture,&m->alpha_ref,&m->blend,&m->su,&m->sv,&m->ou,&m->ov,&m->wrap_s,&m->wrap_t)!=10||index!=i){valid=0;break;}
            m->texture=load_bmp_texture(texture);if(!m->texture)valid=0;
        }fclose(f);
    }
    if(!valid){fprintf(stderr,"[source-skin] rejected invalid source/material data %s\n",path);free_source_skin(s);return 0;}
    s->duration=s->time[s->frames-1];s->ok=1;fprintf(stdout,"[source-skin] %s: %u bones, %u packets, %u vertices, %u timed samples, duration %.3fs\n",path,s->bones,s->packets,s->vertices,s->frames,s->duration);return 1;
}
static void pose_source_skin(SourceSkin*s,float t){
    if(!s->ok)return;
    /* Sparse recorded poses interpolate at their saved tick distances. The
       final sample holds; clip-loop duration is not inferred from a capture. */
    if(t<0)t=0;
    if(t>s->duration)t=s->duration;
    uint32_t a=0;while(a+1<s->frames&&s->time[a+1]<=t)a++;uint32_t b=a+1<s->frames?a+1:a;
    float mix=a==b?0:(t-s->time[a])/(s->time[b]-s->time[a]);
    float matrix[64][12];for(uint32_t j=0;j<s->bones;j++)for(int k=0;k<12;k++)matrix[j][k]=s->matrix[((size_t)a*s->bones+j)*12+k]*(1-mix)+s->matrix[((size_t)b*s->bones+j)*12+k]*mix;
    for(uint32_t i=0;i<s->vertices;i++){
        SourceVertex*v=&s->v[i];V3 p={0,0,0};
        for(uint32_t j=0;j<v->count;j++){const float*m=matrix[v->bone[j]];float w=v->weight[j];p.x+=w*(m[0]*v->p.x+m[1]*v->p.y+m[2]*v->p.z+m[3]);p.y+=w*(m[4]*v->p.x+m[5]*v->p.y+m[6]*v->p.z+m[7]);p.z+=w*(m[8]*v->p.x+m[9]*v->p.y+m[10]*v->p.z+m[11]);}
        s->posed[i]=p;
    }
}
static void draw_source_skin(SourceSkin*s,float x,float z,float yaw,float t){
    if(!s->ok)return;
    pose_source_skin(s,t);
    glPushAttrib(GL_ENABLE_BIT|GL_COLOR_BUFFER_BIT|GL_TEXTURE_BIT|GL_DEPTH_BUFFER_BIT|GL_CURRENT_BIT);
    glEnable(GL_TEXTURE_2D);glDisable(GL_CULL_FACE);
    if(s->flags&8){glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,0);}else glDisable(GL_ALPHA_TEST);
    if(s->flags&4){glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);}else glDisable(GL_BLEND);
    glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_COMBINE);glTexEnvi(GL_TEXTURE_ENV,GL_COMBINE_RGB,GL_MODULATE);glTexEnvi(GL_TEXTURE_ENV,GL_SOURCE0_RGB,GL_TEXTURE);glTexEnvi(GL_TEXTURE_ENV,GL_SOURCE1_RGB,GL_PREVIOUS);glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND0_RGB,GL_SRC_COLOR);glTexEnvi(GL_TEXTURE_ENV,GL_OPERAND1_RGB,GL_SRC_COLOR);glTexEnvi(GL_TEXTURE_ENV,GL_RGB_SCALE,(s->flags&2)?2:1);
    glTexEnvi(GL_TEXTURE_ENV,GL_COMBINE_ALPHA,GL_MODULATE);glTexEnvi(GL_TEXTURE_ENV,GL_SOURCE0_ALPHA,GL_TEXTURE);glTexEnvi(GL_TEXTURE_ENV,GL_SOURCE1_ALPHA,GL_PREVIOUS);
    glPushMatrix();glTranslatef(x,0,z);glRotatef(yaw*180.0f/(float)M_PI,0,1,0);glScalef(s->units,s->units,s->units);glTranslatef(0,-s->floor,0);
    for(uint32_t i=0;i<s->packets;i++){
        SourcePacket*q=&s->packet[i];SourceMaterial*m=&s->material[q->material];glBindTexture(GL_TEXTURE_2D,m->texture);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,m->wrap_s?GL_CLAMP_TO_EDGE:GL_REPEAT);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,m->wrap_t?GL_CLAMP_TO_EDGE:GL_REPEAT);glAlphaFunc(GL_GREATER,m->alpha_ref/255.0f);glBegin(GL_TRIANGLES);
        for(uint32_t j=q->first;j<q->first+q->count;j+=3){V3 n=norm(cross(sub(s->posed[j+1],s->posed[j]),sub(s->posed[j+2],s->posed[j])));float light=.75f+.25f*fmaxf(0,n.y*.7f+n.z*.3f);float color=(s->flags&2)?light*.5f:light;glColor4f(color,color,color,1);
            for(uint32_t k=j;k<j+3;k++){glTexCoord2f(s->v[k].uv.u*m->su+m->ou,s->v[k].uv.v*m->sv+m->ov);glVertex3f(s->posed[k].x,s->posed[k].y,s->posed[k].z);}}
        glEnd();
    }
    glPopMatrix();glPopAttrib();
}
static void write_source_skin_probe_mode(SourceSkin*s,const char*path,int all_frames){
    if(!s->ok)return;
    FILE*f=fopen(path,"wb");if(!f)return;
    uint32_t count=all_frames?s->frames:2;
    for(uint32_t sample=0;sample<count;sample++){uint32_t frame=all_frames?sample:(sample?s->frames-1:0);pose_source_skin(s,s->time[frame]);for(uint32_t i=0;i<s->vertices;i++)fprintf(f,"%u,%u,%.9g,%.9g,%.9g\n",frame,i,s->posed[i].x,s->posed[i].y,s->posed[i].z);}
    fclose(f);
}
static void write_source_skin_probe(SourceSkin*s,const char*path){write_source_skin_probe_mode(s,path,0);}
static V3 source_skin_point(SourceSkin*s,V3 p,float t){
    if(!s->ok||s->bones!=1)return p;
    if(t<0)t=0;
    if(t>s->duration)t=s->duration;
    uint32_t a=0;while(a+1<s->frames&&s->time[a+1]<=t)a++;
    uint32_t b=a+1<s->frames?a+1:a;float f=a==b?0:(t-s->time[a])/(s->time[b]-s->time[a]);float m[12];
    for(int i=0;i<12;i++)m[i]=s->matrix[a*12+i]*(1-f)+s->matrix[b*12+i]*f;
    return (V3){m[0]*p.x+m[1]*p.y+m[2]*p.z+m[3],m[4]*p.x+m[5]*p.y+m[6]*p.z+m[7],m[8]*p.x+m[9]*p.y+m[10]*p.z+m[11]};
}
static V3 source_actor_world(SourceSkin*s,float x,float z,float yaw,V3 p){
    p.x*=s->units;p.y=(p.y-s->floor)*s->units;p.z*=s->units;float sn=sinf(yaw),cs=cosf(yaw);
    return (V3){x+p.x*cs+p.z*sn,p.y,z-p.x*sn+p.z*cs};
}

/* Clips are complete synchronized source pairs. No inferred bone socket,
   30 Hz clock, loop, or region animation is used on this path. */
enum { SOURCE_REFERENCE, SOURCE_AIM, SOURCE_FIRE, SOURCE_MOVE, SOURCE_APPROACH_FIRE, SOURCE_CLIP_COUNT };
static const char *source_clip_labels[SOURCE_CLIP_COUNT]={"reference","aim","fire","move","approach_fire"};
typedef struct { SourceSkin body, weapon; int loaded; } SourceClip;
static SourceClip g_source_clips[SOURCE_CLIP_COUNT];
static int g_source_pair_ready, g_source_active=SOURCE_REFERENCE;
static int g_source_manifest_present, g_source_manifest_accepted, g_source_manifest_rejected;
static float g_source_clip_t;
static unsigned g_source_requested[SOURCE_CLIP_COUNT],g_source_selected[SOURCE_CLIP_COUNT];
static unsigned g_source_fallbacks,g_source_switches,g_source_pair_frames,g_source_pair_sync_failures;
static int source_same_geometry(const SourceSkin*a,const SourceSkin*b){
    return a->ok&&b->ok&&a->bones==b->bones&&a->packets==b->packets&&a->vertices==b->vertices&&a->materials==b->materials&&a->flags==b->flags&&a->units==b->units&&a->floor==b->floor&&
        !memcmp(a->parent,b->parent,a->bones*sizeof *a->parent)&&!memcmp(a->packet,b->packet,a->packets*sizeof *a->packet)&&!memcmp(a->v,b->v,a->vertices*sizeof *a->v);
}
static int source_pair_matches(const SourceSkin*body,const SourceSkin*weapon){
    return body->ok&&weapon->ok&&body->bones==44&&body->packets==106&&body->vertices==3456&&weapon->bones==1&&weapon->vertices==243&&
        body->frames==weapon->frames&&body->units==weapon->units&&body->floor==weapon->floor&&body->time[0]==0&&
        !memcmp(body->time,weapon->time,body->frames*sizeof *body->time);
}
static SourceSkin *source_active_body(void){return g_source_clips[g_source_active].loaded?&g_source_clips[g_source_active].body:&g_aya_source;}
static SourceSkin *source_active_weapon(void){return g_source_clips[g_source_active].loaded?&g_source_clips[g_source_active].weapon:&g_weapon_source;}
static int source_clip_available(int id){return id==SOURCE_REFERENCE?g_source_pair_ready:g_source_clips[id].loaded;}
static int source_clip_choice(int requested){
    if(source_clip_available(requested))return requested;
    if(requested==SOURCE_FIRE&&source_clip_available(SOURCE_AIM))return SOURCE_AIM;
    if(requested==SOURCE_APPROACH_FIRE&&source_clip_available(SOURCE_FIRE))return SOURCE_FIRE;
    return SOURCE_REFERENCE;
}
static int source_clip_path(char out[512],const char*relative){
    char normalized[480];size_t n=strlen(relative);if(!n||n>=sizeof normalized)return 0;
    for(size_t i=0;i<=n;i++)normalized[i]=relative[i]=='\\'?'/':relative[i];
    if(normalized[0]=='/'||strchr(normalized,':'))return 0;
    const char*p=normalized;while(*p){const char*end=strchr(p,'/');size_t len=end?(size_t)(end-p):strlen(p);if(!len||(len==1&&p[0]=='.')||(len==2&&p[0]=='.'&&p[1]=='.'))return 0;if(!end)break;p=end+1;}
    int size=snprintf(out,512,"%s%s",!strncmp(normalized,"assets/models/",14)?"":"assets/models/",normalized);return size>0&&size<512;
}
static void free_source_clips(void){
    for(int i=0;i<SOURCE_CLIP_COUNT;i++){free_source_skin(&g_source_clips[i].body);free_source_skin(&g_source_clips[i].weapon);g_source_clips[i].loaded=0;}
}
static void load_source_clips(const char*manifest){
    g_source_pair_ready=source_pair_matches(&g_aya_source,&g_weapon_source);
    if(!g_source_pair_ready){fprintf(stderr,"[source-clips] reference pair missing or inconsistent; using legacy fallback\n");free_source_skin(&g_aya_source);free_source_skin(&g_weapon_source);return;}
    FILE*f=fopen(manifest,"rb");if(!f){fprintf(stdout,"[source-clips] optional manifest absent; reference pair only\n");return;}
    g_source_manifest_present=1;char tag[32];unsigned count=0;int valid=fscanf(f,"%31s %u",tag,&count)==2&&!strcmp(tag,"T3BCLIPS1")&&count<=SOURCE_CLIP_COUNT;
    for(unsigned i=0;i<count&&valid;i++){
        char label[32],body_relative[480],weapon_relative[480],body_path[512],weapon_path[512];int id=-1;
        if(fscanf(f,"%31s %479s %479s",label,body_relative,weapon_relative)!=3){valid=0;break;}
        for(int j=0;j<SOURCE_CLIP_COUNT;j++)if(!strcmp(label,source_clip_labels[j]))id=j;
        if(id<0||g_source_clips[id].loaded||!source_clip_path(body_path,body_relative)||!source_clip_path(weapon_path,weapon_relative)){valid=0;break;}
        SourceClip*c=&g_source_clips[id];
        valid=load_source_skin(&c->body,body_path,aya_material_path())&&
            load_source_skin(&c->weapon,weapon_path,weapon_material_path())&&
            source_pair_matches(&c->body,&c->weapon)&&source_same_geometry(&g_aya_source,&c->body)&&source_same_geometry(&g_weapon_source,&c->weapon);
        c->loaded=valid;
        if(!valid)fprintf(stderr,"[source-clips] rejected %s: source pair timing, geometry, units, or material mismatch\n",label);
    }
    char extra[2];if(valid&&fscanf(f,"%1s",extra)==1)valid=0;fclose(f);
    if(!valid){free_source_clips();g_source_manifest_rejected=1;fprintf(stderr,"[source-clips] manifest rejected atomically; reference pair retained\n");}
    else{g_source_manifest_accepted=1;fprintf(stdout,"[source-clips] accepted %u optional synchronized pairs\n",count);}
}
static void update_source_clip(float dt,int locked,int firing,int moving){
    if(!g_source_pair_ready)return;
    int requested=(firing&&moving)?SOURCE_APPROACH_FIRE:(firing?SOURCE_FIRE:(locked?SOURCE_AIM:(moving?SOURCE_MOVE:SOURCE_REFERENCE)));
    int selected=source_clip_choice(requested);g_source_requested[requested]++;g_source_selected[selected]++;
    if(selected!=requested)g_source_fallbacks++;
    if(selected!=g_source_active){g_source_active=selected;g_source_clip_t=0;g_source_switches++;}
    else{g_source_clip_t+=dt;if(g_source_clip_t>source_active_body()->duration)g_source_clip_t=source_active_body()->duration;}
    g_source_pair_frames++;
    if(!source_pair_matches(source_active_body(),source_active_weapon()))g_source_pair_sync_failures++;
}
static void write_source_clip_result(FILE*f){
    fprintf(f,"source_pair_ready=%d\nsource_clip_manifest_present=%d\nsource_clip_manifest_accepted=%d\nsource_clip_manifest_rejected=%d\nsource_active_clip=%s\nsource_clip_time=%.9g\nsource_clip_switches=%u\nsource_clip_fallback_frames=%u\nsource_pair_synchronized_frames=%u\nsource_pair_sync_failures=%u\nsource_clip_playback_clamp=1\nsource_clip_legacy_30hz=0\n",g_source_pair_ready,g_source_manifest_present,g_source_manifest_accepted,g_source_manifest_rejected,source_clip_labels[g_source_active],g_source_clip_t,g_source_switches,g_source_fallbacks,g_source_pair_frames,g_source_pair_sync_failures);
    for(int i=0;i<SOURCE_CLIP_COUNT;i++)fprintf(f,"source_clip_%s_available=%d\nsource_clip_%s_requested_frames=%u\nsource_clip_%s_selected_frames=%u\n",source_clip_labels[i],source_clip_available(i),source_clip_labels[i],g_source_requested[i],source_clip_labels[i],g_source_selected[i]);
    /* Small selector checks only. They do not assert that a recorded capture
       depicts the named action or that gameplay/visual alignment passed. */
    int failures=0;for(int i=0;i<SOURCE_CLIP_COUNT;i++){int expected=source_clip_available(i)?i:(i==SOURCE_FIRE&&source_clip_available(SOURCE_AIM)?SOURCE_AIM:(i==SOURCE_APPROACH_FIRE&&source_clip_available(SOURCE_FIRE)?SOURCE_FIRE:SOURCE_REFERENCE));if(source_clip_choice(i)!=expected)failures++;}
    fprintf(f,"source_clip_selector_checks=5\nsource_clip_selector_failures=%d\nsource_muzzle_origin=weapon_mesh_tip_candidate\n",failures);
}
