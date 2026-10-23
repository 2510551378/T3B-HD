#include <SDL.h>
#include <SDL_opengl.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { float x, y, z; } V3;
typedef struct { int a, b, c; } Tri;
typedef struct { V3 *v; size_t nv, cv; Tri *t; size_t nt, ct; V3 lo, hi, center; float radius; } Obj;

static void die(const char *msg) { fprintf(stderr, "[t3b_hd] %s\n", msg); exit(1); }
static void *grow(void *p, size_t *cap, size_t need, size_t elem) {
    if (need <= *cap) return p;
    size_t n = *cap ? *cap : 4096;
    while (n < need) n *= 2;
    void *q = realloc(p, n * elem);
    if (!q) die("out of memory");
    *cap = n;
    return q;
}
static int obj_index(const char *s, int n) {
    char *e = NULL; long k = strtol(s, &e, 10);
    if (e == s || k == 0) return -1;
    if (k < 0) k = (long)n + k + 1;
    return (int)k - 1;
}
static int face_index(char *tok, int n) {
    char *slash = strchr(tok, '/');
    if (slash) *slash = 0;
    return obj_index(tok, n);
}
static Obj load_obj(const char *path) {
    Obj o; memset(&o, 0, sizeof o);
    o.lo = (V3){1e30f,1e30f,1e30f}; o.hi = (V3){-1e30f,-1e30f,-1e30f};
    FILE *f = fopen(path, "rb"); if (!f) { fprintf(stderr, "[t3b_hd] cannot open %s\n", path); exit(1); }
    char line[1024];
    while (fgets(line, sizeof line, f)) {
        if (line[0] == 'v' && line[1] == ' ') {
            V3 p; if (sscanf(line + 2, "%f %f %f", &p.x, &p.y, &p.z) != 3) continue;
            o.v = grow(o.v, &o.cv, o.nv + 1, sizeof *o.v); o.v[o.nv++] = p;
            if (p.x < o.lo.x) o.lo.x = p.x;
            if (p.y < o.lo.y) o.lo.y = p.y;
            if (p.z < o.lo.z) o.lo.z = p.z;
            if (p.x > o.hi.x) o.hi.x = p.x;
            if (p.y > o.hi.y) o.hi.y = p.y;
            if (p.z > o.hi.z) o.hi.z = p.z;
        } else if (line[0] == 'f' && line[1] == ' ') {
            char a[64], b[64], c[64], d[64]; int n = sscanf(line + 2, "%63s %63s %63s %63s", a,b,c,d);
            if (n < 3) continue;
            int ia = face_index(a, (int)o.nv), ib = face_index(b, (int)o.nv), ic = face_index(c, (int)o.nv);
            if (ia < 0 || ib < 0 || ic < 0 || ia >= (int)o.nv || ib >= (int)o.nv || ic >= (int)o.nv) continue;
            o.t = grow(o.t, &o.ct, o.nt + 1, sizeof *o.t); o.t[o.nt++] = (Tri){ia,ib,ic};
            if (n == 4) { int id = face_index(d, (int)o.nv); if (id >= 0 && id < (int)o.nv) { o.t = grow(o.t, &o.ct, o.nt + 1, sizeof *o.t); o.t[o.nt++] = (Tri){ia,ic,id}; } }
        }
    }
    fclose(f);
    if (!o.nv || !o.nt) die("OBJ has no vertices or triangles");
    o.center = (V3){(o.lo.x + o.hi.x)*0.5f, (o.lo.y + o.hi.y)*0.5f, (o.lo.z + o.hi.z)*0.5f};
    float dx=o.hi.x-o.lo.x, dy=o.hi.y-o.lo.y, dz=o.hi.z-o.lo.z;
    o.radius = fmaxf(dx, fmaxf(dy, dz)); if (o.radius < 0.001f) o.radius = 1.0f;
    fprintf(stdout, "[asset] %s: %llu vertices, %llu triangles, bbox %.2f x %.2f x %.2f\n", path,
            (unsigned long long)o.nv, (unsigned long long)o.nt, dx,dy,dz);
    return o;
}
static V3 sub(V3 a, V3 b) { return (V3){a.x-b.x,a.y-b.y,a.z-b.z}; }
static V3 cross(V3 a, V3 b) { return (V3){a.y*b.z-a.z*b.y, a.z*b.x-a.x*b.z, a.x*b.y-a.y*b.x}; }
static V3 norm(V3 a) { float n=sqrtf(a.x*a.x+a.y*a.y+a.z*a.z); if(n<1e-8f)return (V3){0,1,0}; return (V3){a.x/n,a.y/n,a.z/n}; }
static void screenshot(const char *path, int w, int h) {
    size_t n = (size_t)w * (size_t)h * 3; unsigned char *pix = (unsigned char *)malloc(n);
    if (!pix) return;
    glPixelStorei(GL_PACK_ALIGNMENT, 1); glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE, pix);
    FILE *f = fopen(path, "wb");
    if (f) {
        fprintf(f, "P6\n%d %d\n255\n", w, h);
        for (int y=h-1; y>=0; y--) fwrite(pix + (size_t)y*w*3, 1, (size_t)w*3, f);
        fclose(f); fprintf(stdout, "[shot] %s\n", path);
    }
    free(pix);
}
static void draw_obj(const Obj *o) {
    glBegin(GL_TRIANGLES);
    for (size_t i=0;i<o->nt;i++) {
        Tri q=o->t[i]; V3 a=o->v[q.a], b=o->v[q.b], c=o->v[q.c];
        V3 n=norm(cross(sub(b,a),sub(c,a))); float light=0.35f+0.65f*fmaxf(0.0f,n.y*0.7f+n.z*0.3f);
        float h=((a.y+b.y+c.y)/3.0f-o->lo.y)/(o->hi.y-o->lo.y+1e-6f);
        float r=(0.20f+0.08f*h)*light, g=(0.30f+0.12f*h)*light, bl=(0.34f+0.18f*h)*light;
        glColor3f(r,g,bl);
        glVertex3f(a.x-o->center.x,a.y-o->center.y,a.z-o->center.z);
        glVertex3f(b.x-o->center.x,b.y-o->center.y,b.z-o->center.z);
        glVertex3f(c.x-o->center.x,c.y-o->center.y,c.z-o->center.z);
    }
    glEnd();
}
static void perspective(float fovy, float aspect, float znear, float zfar) {
    float t=tanf(fovy*0.5f*(float)M_PI/180.0f)*znear, r=t*aspect;
    glFrustum(-r,r,-t,t,znear,zfar);
}
int main(int argc, char **argv) {
    const char *asset = argc > 1 ? argv[1] : "..\\psp_parse\\out\\meshes\\pack_0x4c199000.obj";
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) < 0) die(SDL_GetError());
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2); SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1); SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    SDL_Window *win = SDL_CreateWindow("The 3rd Birthday HD Remaster - M0", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 1920,1080, SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE);
    if (!win) die(SDL_GetError());
    SDL_GLContext ctx=SDL_GL_CreateContext(win); if(!ctx) die(SDL_GetError()); SDL_GL_SetSwapInterval(1);
    Obj obj=load_obj(asset); int run=1; float yaw=35.0f,pitch=20.0f,dist=2.8f; Uint64 prev=SDL_GetPerformanceCounter(); int frames=0; double fps_t=0;
    const char *shot_path=getenv("T3B_HD_SCREENSHOT"); const char *exit_text=getenv("T3B_HD_EXIT_FRAMES"); int shot_done=0; int exit_frames=exit_text?atoi(exit_text):0; int total_frames=0;
    glEnable(GL_DEPTH_TEST); glDisable(GL_CULL_FACE); glEnable(GL_FOG); { GLfloat c[4]={0.035f,0.055f,0.065f,1}; glFogfv(GL_FOG_COLOR,c); glFogi(GL_FOG_MODE,GL_LINEAR); glFogf(GL_FOG_START,6.0f); glFogf(GL_FOG_END,18.0f); }
    while(run) {
        Uint64 now=SDL_GetPerformanceCounter(); float dt=(float)((now-prev)/(double)SDL_GetPerformanceFrequency()); prev=now; if(dt>0.1f)dt=0.1f;
        SDL_Event e; const Uint8 *keys=SDL_GetKeyboardState(NULL);
        while(SDL_PollEvent(&e)) { if(e.type==SDL_QUIT)run=0; if(e.type==SDL_KEYDOWN && e.key.keysym.sym==SDLK_ESCAPE)run=0; if(e.type==SDL_MOUSEWHEEL)dist*=e.wheel.y<0?1.1f:0.9f; }
        if(keys[SDL_SCANCODE_A]) yaw -= 45*dt;
        if(keys[SDL_SCANCODE_D]) yaw += 45*dt;
        if(keys[SDL_SCANCODE_W]) pitch += 35*dt;
        if(keys[SDL_SCANCODE_S]) pitch -= 35*dt;
        if(keys[SDL_SCANCODE_Q]) dist *= 1.0f + dt;
        if(keys[SDL_SCANCODE_E]) dist *= 1.0f - dt;
        if(pitch>80) pitch=80;
        if(pitch<-80) pitch=-80;
        if(dist<1.05f) dist=1.05f;
        if(dist>8) dist=8;
        int w,h; SDL_GetWindowSize(win,&w,&h); glViewport(0,0,w,h); glClearColor(0.012f,0.018f,0.022f,1); glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
        glMatrixMode(GL_PROJECTION); glLoadIdentity(); perspective(55.0f,(float)w/(float)h,0.03f,80.0f); glMatrixMode(GL_MODELVIEW); glLoadIdentity();
        glTranslatef(0,0,-dist); glRotatef(-pitch,1,0,0); glRotatef(-yaw,0,1,0);
        float s=4.5f/obj.radius; glScalef(s,s,s); draw_obj(&obj); SDL_GL_SwapWindow(win);
        total_frames++; frames++; fps_t+=dt;
        if (shot_path && !shot_done && total_frames >= 30) { screenshot(shot_path, w, h); shot_done=1; }
        if (exit_frames > 0 && total_frames >= exit_frames) run=0;
        if(fps_t>1.0){char title[160]; snprintf(title,sizeof title,"The 3rd Birthday HD Remaster - M0 | %.0f FPS | %llu tris | WASD orbit Q/E zoom",frames/fps_t,(unsigned long long)obj.nt); SDL_SetWindowTitle(win,title); frames=0; fps_t=0;}
    }
    free(obj.v); free(obj.t); SDL_GL_DeleteContext(ctx); SDL_DestroyWindow(win); SDL_Quit(); return 0;
}
