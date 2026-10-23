/* Render-only original street. Positions already use the exporter's original
   WORLD -> inverse Aya WORLD -> canonical scale/floor transform. Never center
   or rescale them here. Collision, original fog/stencil, and event state are
   not recovered by this renderer. */
typedef struct { V3 p; V2 uv; uint8_t rgba[4]; } OriginalSceneVertex;
typedef struct { uint32_t first,count,material; } OriginalSceneDraw;
typedef struct { GLuint texture; int blend,depth_write,cull; } OriginalSceneMaterial;
typedef struct {
    OriginalSceneVertex *v;OriginalSceneDraw *draw;OriginalSceneMaterial *material;
    uint32_t vertices,draws,materials;float player[3],enemy[3],units,floor;
    uint64_t vertex_hash,loaded_vertex_hash,uv_rgba_hash;
    unsigned rendered_frames,rendered_draws,probe_vertices,nonwhite_vertices,nonopaque_vertices,context_gl_errors;
    int ok;
} OriginalScene;
static OriginalScene g_original_scene;
static int g_original_scene_collision_adapter_enabled;
static uint64_t original_scene_hash(uint64_t hash,const uint8_t*data,size_t size){
    for(size_t i=0;i<size;i++){hash^=data[i];hash*=UINT64_C(1099511628211);}return hash;
}
static void free_original_scene(void){
    for(uint32_t i=0;i<g_original_scene.materials;i++)if(g_original_scene.material&&g_original_scene.material[i].texture)glDeleteTextures(1,&g_original_scene.material[i].texture);
    free(g_original_scene.v);free(g_original_scene.draw);free(g_original_scene.material);memset(&g_original_scene,0,sizeof g_original_scene);
}
static int original_scene_relative_path(const char*path){
    if(!*path||path[0]=='/'||path[0]=='\\'||strchr(path,':'))return 0;
    const char*p=path;while(*p){const char*end=p;while(*end&&*end!='/'&&*end!='\\')end++;size_t length=(size_t)(end-p);if(!length||(length==1&&p[0]=='.')||(length==2&&p[0]=='.'&&p[1]=='.'))return 0;p=*end?end+1:end;}return 1;
}
static int load_original_scene(void){
    OriginalScene*s=&g_original_scene;size_t size=0;uint8_t*d=read_file("assets/scenes/original_street/original_street.bin",&size);
    if(!d){fprintf(stderr,"[original-scene] original street missing; legacy scene fallback\n");return 0;}
    if(size<56||memcmp(d,"T3BSCN1\0",8)||rd32(d+8)!=1||rd32(d+12)!=140||rd32(d+16)!=31656||rd32(d+20)!=81){free(d);fprintf(stderr,"[original-scene] rejected unexpected street header\n");return 0;}
    s->draws=rd32(d+12);s->vertices=rd32(d+16);s->materials=rd32(d+20);
    size_t expected=56+(size_t)s->draws*12+(size_t)s->vertices*24;
    if(size!=expected){free(d);free_original_scene();fprintf(stderr,"[original-scene] rejected street byte count\n");return 0;}
    int valid=1;float values[8];for(int i=0;i<8;i++){values[i]=source_f32(d+24+i*4);if(!isfinite(values[i]))valid=0;}
    memcpy(s->player,values,12);memcpy(s->enemy,values+3,12);s->units=values[6];s->floor=values[7];if(!(s->units>0))valid=0;
    s->v=calloc(s->vertices,sizeof *s->v);s->draw=calloc(s->draws,sizeof *s->draw);s->material=calloc(s->materials,sizeof *s->material);
    if(!s->v||!s->draw||!s->material)die("original scene allocation failed");
    size_t offset=56;uint32_t next=0;
    for(uint32_t i=0;i<s->draws;i++,offset+=12){OriginalSceneDraw*q=&s->draw[i];q->first=rd32(d+offset);q->count=rd32(d+offset+4);q->material=rd32(d+offset+8);
        if(q->first!=next||next>s->vertices||!q->count||q->count%3||q->count>s->vertices-next||q->material>=s->materials)valid=0;
        if(q->count>s->vertices-next){valid=0;break;}next+=q->count;
    }
    if(next!=s->vertices)valid=0;
    /* Keep parsing at the canonical vertex offset even after an invalid draw. */
    offset=56+(size_t)s->draws*12;s->vertex_hash=UINT64_C(14695981039346656037);s->loaded_vertex_hash=s->vertex_hash;s->uv_rgba_hash=s->vertex_hash;
    for(uint32_t i=0;i<s->vertices;i++,offset+=24){
        float f[5];for(int j=0;j<5;j++){f[j]=source_f32(d+offset+j*4);if(!isfinite(f[j]))valid=0;}
        OriginalSceneVertex*v=&s->v[i];v->p=(V3){f[0],f[1],f[2]};v->uv=(V2){f[3],f[4]};memcpy(v->rgba,d+offset+20,4);
        if(v->rgba[0]!=255||v->rgba[1]!=255||v->rgba[2]!=255)s->nonwhite_vertices++;
        if(v->rgba[3]!=255)s->nonopaque_vertices++;
        s->vertex_hash=original_scene_hash(s->vertex_hash,d+offset,24);s->uv_rgba_hash=original_scene_hash(s->uv_rgba_hash,d+offset+12,12);
        float stored[5]={v->p.x,v->p.y,v->p.z,v->uv.u,v->uv.v};uint8_t loaded[24];for(int j=0;j<5;j++){uint32_t bits;memcpy(&bits,&stored[j],4);for(int b=0;b<4;b++)loaded[j*4+b]=(uint8_t)(bits>>(8*b));}memcpy(loaded+20,v->rgba,4);
        s->loaded_vertex_hash=original_scene_hash(s->loaded_vertex_hash,loaded,sizeof loaded);
    }
    free(d);if(s->vertex_hash!=s->loaded_vertex_hash)valid=0;
    FILE*f=fopen("assets/scenes/original_street/original_street_materials.txt","rb");char tag[32];unsigned count=0;
    if(!f)valid=0;
    if(f){
        if(fscanf(f,"%31s %u",tag,&count)!=2||strcmp(tag,"T3BSCNM1")||count!=s->materials)valid=0;
        for(uint32_t i=0;i<s->materials&&valid;i++){char path[512];OriginalSceneMaterial*m=&s->material[i];
            if(fscanf(f,"%511s %d %d %d",path,&m->blend,&m->depth_write,&m->cull)!=4||!original_scene_relative_path(path)||
                (m->blend!=0&&m->blend!=1)||(m->depth_write!=0&&m->depth_write!=1)||(m->cull!=0&&m->cull!=1)){valid=0;break;}
            m->texture=load_bmp_texture(path);if(!m->texture)valid=0;
        }
        char extra[2];if(valid&&fscanf(f,"%1s",extra)==1)valid=0;fclose(f);
    }
    if(!valid){fprintf(stderr,"[original-scene] rejected incomplete/invalid geometry or materials; legacy scene fallback\n");free_original_scene();return 0;}
    s->ok=1;fprintf(stdout,"[original-scene] loaded %u draws, %u vertices, %u original materials\n",s->draws,s->vertices,s->materials);return 1;
}
static void draw_original_scene(void){
    OriginalScene*s=&g_original_scene;if(!s->ok)return;
    glPushAttrib(GL_ENABLE_BIT|GL_COLOR_BUFFER_BIT|GL_TEXTURE_BIT|GL_DEPTH_BUFFER_BIT|GL_CURRENT_BIT|GL_POLYGON_BIT|GL_LIGHTING_BIT);
    glDisable(GL_LIGHTING);glDisable(GL_FOG);glDisable(GL_STENCIL_TEST);glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LEQUAL);glDepthRange(0,1);
    glEnable(GL_TEXTURE_2D);glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,0);glShadeModel(GL_SMOOTH);
    glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_MODULATE);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    /* Preserved roads have +Y normals and all export transforms have positive
       determinant. From above, standard RH look_at/glFrustum sees CCW fronts. */
    glFrontFace(GL_CCW);glCullFace(GL_BACK);
    for(uint32_t i=0;i<s->draws;i++){
        OriginalSceneDraw*q=&s->draw[i];OriginalSceneMaterial*m=&s->material[q->material];
        if(m->blend)glEnable(GL_BLEND);else glDisable(GL_BLEND);
        if(m->cull)glEnable(GL_CULL_FACE);else glDisable(GL_CULL_FACE);
        glDepthMask(m->depth_write?GL_TRUE:GL_FALSE);glBindTexture(GL_TEXTURE_2D,m->texture);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_REPEAT);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_REPEAT);
        glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
        glBegin(GL_TRIANGLES);for(uint32_t j=q->first;j<q->first+q->count;j++){OriginalSceneVertex*v=&s->v[j];glColor4ub(v->rgba[0],v->rgba[1],v->rgba[2],v->rgba[3]);glTexCoord2f(v->uv.u,v->uv.v);glVertex3f(v->p.x,v->p.y,v->p.z);}glEnd();
        s->rendered_draws++;
    }
    s->rendered_frames++;glPopAttrib();if(glGetError()!=GL_NO_ERROR)s->context_gl_errors++;
}
static void write_original_scene_probe(void){
    OriginalScene*s=&g_original_scene;if(!s->ok)return;FILE*f=fopen("build/original_scene_probe.csv","wb");if(!f)return;
    fprintf(f,"vertex,draw,material,x,y,z,u,v,r,g,b,a,xbits,ybits,zbits,ubits,vbits\n");
    for(uint32_t i=0;i<s->draws;i++){OriginalSceneDraw*q=&s->draw[i];for(uint32_t j=q->first;j<q->first+q->count;j++){
        OriginalSceneVertex*v=&s->v[j];float values[5]={v->p.x,v->p.y,v->p.z,v->uv.u,v->uv.v};uint32_t bits[5];memcpy(bits,values,sizeof bits);
        fprintf(f,"%u,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%u,%u,%u,%u,%08x,%08x,%08x,%08x,%08x\n",j,i,q->material,v->p.x,v->p.y,v->p.z,v->uv.u,v->uv.v,v->rgba[0],v->rgba[1],v->rgba[2],v->rgba[3],bits[0],bits[1],bits[2],bits[3],bits[4]);s->probe_vertices++;
    }}fclose(f);
}
static void write_original_scene_result(FILE*f){
    OriginalScene*s=&g_original_scene;
    fprintf(f,"original_scene_enabled=%d\noriginal_scene_draws=%u\noriginal_scene_vertices=%u\noriginal_scene_triangles=%u\noriginal_scene_materials=%u\noriginal_scene_rendered_frames=%u\noriginal_scene_rendered_draws=%u\noriginal_scene_probe_vertices=%u\noriginal_scene_nonwhite_vertices=%u\noriginal_scene_nonopaque_vertices=%u\noriginal_scene_vertex_fnv64=%016llx\noriginal_scene_loaded_vertex_fnv64=%016llx\noriginal_scene_uv_rgba_fnv64=%016llx\ncollision_recovered=0\noriginal_scene_depth=LEQUAL\noriginal_scene_front_face=CCW\noriginal_scene_source_winding_preserved=1\noriginal_scene_vertex_color=original_RGBA_MODULATE\noriginal_scene_fog_supported=0\noriginal_scene_stencil_supported=0\noriginal_scene_all_render_state_recovered=0\n",s->ok,s->draws,s->vertices,s->vertices/3,s->materials,s->rendered_frames,s->rendered_draws,s->probe_vertices,s->nonwhite_vertices,s->nonopaque_vertices,(unsigned long long)s->vertex_hash,(unsigned long long)s->loaded_vertex_hash,(unsigned long long)s->uv_rgba_hash);
    if(s->ok)fprintf(f,"original_scene_units=%.9g\noriginal_scene_floor=%.9g\noriginal_scene_player_spawn=%.9g,%.9g,%.9g\noriginal_scene_enemy_spawn=%.9g,%.9g,%.9g\n",s->units,s->floor,s->player[0],s->player[1],s->player[2],s->enemy[0],s->enemy[1],s->enemy[2]);
    fprintf(f,"original_scene_context_gl_errors=%u\n",s->context_gl_errors);
    fprintf(f,"scene_render_only=%d\noriginal_scene_behavior_recovered=0\n",g_original_scene_collision_adapter_enabled?0:1);
}
