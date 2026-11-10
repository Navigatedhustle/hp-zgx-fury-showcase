/* Apache-2.0. PNG stream to H.264 MP4 with pinned permissive codec libraries. */
#define _POSIX_C_SOURCE 200809L
#define H264E_MAX_THREADS 0
#define STBI_ONLY_PNG
#include "minih264e.h"
#include "minimp4.h"
#include "stb_image.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static void fail(const char *message) { fprintf(stderr, "%s\n", message); exit(1); }
static void *aligned_memory(size_t size) { void *p = NULL; if (posix_memalign(&p,64,size)) fail("Allocation failed"); return p; }
static unsigned be32(const unsigned char *p) { return ((unsigned)p[0]<<24)|((unsigned)p[1]<<16)|((unsigned)p[2]<<8)|p[3]; }
static int write_mp4(int64_t offset,const void *data,size_t size,void *token) {
    FILE *file=token;
    return fseek(file,(long)offset,SEEK_SET) || fwrite(data,1,size,file)!=size;
}
static unsigned char *read_png(size_t *size) {
    unsigned char signature[8];
    size_t got=fread(signature,1,8,stdin);
    if (!got) return NULL;
    if (got!=8 || memcmp(signature,"\x89PNG\r\n\x1a\n",8)) fail("Invalid PNG stream");
    size_t used=8,capacity=65536;
    unsigned char *buffer=malloc(capacity); if (!buffer) fail("Allocation failed");
    memcpy(buffer,signature,8);
    for (;;) {
        unsigned char chunk[8]; if (fread(chunk,1,8,stdin)!=8) fail("Truncated PNG header");
        unsigned length=be32(chunk);
        if (length>64*1024*1024 || used+length+12>64*1024*1024) fail("PNG too large");
        if (used+length+12>capacity) { capacity=used+length+12; buffer=realloc(buffer,capacity); if (!buffer) fail("Allocation failed"); }
        memcpy(buffer+used,chunk,8);
        if (fread(buffer+used+8,1,length+4,stdin)!=length+4) fail("Truncated PNG data");
        used+=length+12;
        if (!memcmp(chunk+4,"IEND",4)) break;
    }
    *size=used; return buffer;
}
static void convert_yuv(const unsigned char *rgb,unsigned char *out,int w,int h) {
    unsigned char *u=out+w*h,*v=u+w*h/4;
    for (int y=0;y<h;y++) for (int x=0;x<w;x++) {
        const unsigned char *p=rgb+(y*w+x)*3;
        out[y*w+x]=(unsigned char)(16+((66*p[0]+129*p[1]+25*p[2]+128)>>8));
    }
    for (int y=0;y<h;y+=2) for (int x=0;x<w;x+=2) {
        int r=0,g=0,b=0;
        for (int dy=0;dy<2;dy++) for (int dx=0;dx<2;dx++) {const unsigned char *p=rgb+((y+dy)*w+x+dx)*3;r+=p[0];g+=p[1];b+=p[2];}
        r=(r+2)/4;g=(g+2)/4;b=(b+2)/4;
        *u++=(unsigned char)(128+((-38*r-74*g+112*b+128)>>8));
        *v++=(unsigned char)(128+((112*r-94*g-18*b+128)>>8));
    }
}
int main(int argc,char **argv) {
    if (argc!=3 || strcmp(argv[2],"veryfast")) fail("Usage: encode OUTPUT.mp4 veryfast < frames.pngstream");
    FILE *file=fopen(argv[1],"wb"); if (!file) fail("Cannot create MP4");
    MP4E_mux_t *mux=MP4E_open(0,0,file,write_mp4); if (!mux) fail("Cannot create MP4 mux");
    mp4_h26x_writer_t writer;
    H264E_persist_t *encoder=NULL; H264E_scratch_t *scratch=NULL;
    H264E_create_param_t params={0}; H264E_run_param_t run={0}; H264E_io_yuv_t yuv={0};
    unsigned char *planes=NULL; int width=0,height=0,frames=0;
    for (;;) {
        size_t size;unsigned char *png=read_png(&size);if(!png)break;
        int w,h,channels;unsigned char *rgb=stbi_load_from_memory(png,(int)size,&w,&h,&channels,3);free(png);
        if(!rgb || w<16 || h<16 || w>3840 || h>2160 || (w|h)&1)fail("Unsupported video frame");
        if(!encoder) {
            width=w;height=h;params.width=w;params.height=h;params.gop=30;params.const_input_flag=1;params.enableNEON=1;params.num_layers=1;
            int persistent_bytes,scratch_bytes;
            if(H264E_sizeof(&params,&persistent_bytes,&scratch_bytes))fail("H264 dimensions rejected");
            encoder=aligned_memory(persistent_bytes);scratch=aligned_memory(scratch_bytes);
            if(H264E_init(encoder,&params))fail("H264 initialization failed");
            planes=aligned_memory((size_t)w*h*3/2);
            yuv.yuv[0]=planes;yuv.yuv[1]=planes+w*h;yuv.yuv[2]=planes+w*h*5/4;
            yuv.stride[0]=w;yuv.stride[1]=yuv.stride[2]=w/2;
            if(mp4_h26x_write_init(&writer,mux,w,h,0))fail("MP4 track initialization failed");
            run.encode_speed=8;run.qp_min=run.qp_max=20;
        }
        if(w!=width || h!=height)fail("Video frame dimensions changed");
        convert_yuv(rgb,planes,w,h);stbi_image_free(rgb);
        unsigned char *data;int bytes;
        if(H264E_encode(encoder,scratch,&run,&yuv,&data,&bytes))fail("H264 frame encoding failed");
        if(mp4_h26x_write_nal(&writer,data,bytes,90000/30))fail("MP4 sample write failed");
        frames++;
    }
    if(!frames)fail("No video frames received");
    MP4E_close(mux);mp4_h26x_write_close(&writer);fclose(file);free(encoder);free(scratch);free(planes);
    fprintf(stderr,"Encoded %d frames at 30 fps, veryfast (minih264 speed 8), %dx%d\n",frames,width,height);
    return 0;
}
