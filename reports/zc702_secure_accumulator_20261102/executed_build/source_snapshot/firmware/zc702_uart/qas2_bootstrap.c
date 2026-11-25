#include "qas2_bootstrap.h"
#include "../crypto/qcrypto.h"
#include <string.h>
enum{QB_CLOSED=0,QB_NEW=1,QB_WAIT=2,QB_ESTABLISHED=3,QB_CONSUMED=4};
static int same(const uint8_t *a,const uint8_t *b,size_t n){uint8_t d=0;for(size_t i=0;i<n;i++)d|=a[i]^b[i];return d==0;}
static int nonzero(const uint8_t *p,size_t n){uint8_t d=0;for(size_t i=0;i<n;i++)d|=p[i];return d!=0;}
static uint32_t get32(const uint8_t *p){uint32_t v=0;for(unsigned i=0;i<4;i++)v|=(uint32_t)p[i]<<(8*i);return v;}
static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
void qboot_abort(qboot_context *ctx){if(ctx)qcrypto_wipe(ctx,sizeof(*ctx));}
static int fail(qboot_context *ctx){qboot_abort(ctx);return -1;}
static int tag(const uint8_t key[32],const char *label,const uint8_t *body,size_t n,uint8_t out[32]){
    static const char prefix[]="QKD/QAS2/bootstrap/v1/";uint8_t buffer[256];
    size_t prefix_n=sizeof(prefix)-1,label_n=strlen(label),total=prefix_n+label_n+1+n;
    if(total>sizeof(buffer))return -1;
    memcpy(buffer,prefix,prefix_n);memcpy(buffer+prefix_n,label,label_n+1);memcpy(buffer+prefix_n+label_n+1,body,n);
    int rc=qcrypto_hmac(key,32,buffer,total,out);qcrypto_wipe(buffer,sizeof(buffer));return rc;
}
static int derive(qboot_context *ctx,const char *purpose,uint8_t *out,size_t n){
    static const char prefix[]="QKD/QAS2/session/v1/";uint8_t info[128],salt[64];
    size_t at=sizeof(prefix)-1,p_n=strlen(purpose);if(at+33+p_n>sizeof(info))return -1;
    memcpy(info,prefix,at);memcpy(info+at,ctx->transcript,32);at+=32;info[at++]='/';
    memcpy(info+at,purpose,p_n);at+=p_n;memcpy(salt,ctx->na,32);memcpy(salt+32,ctx->nb,32);
    int rc=qcrypto_hkdf(ctx->psk,32,salt,64,info,at,out,n);qcrypto_wipe(info,sizeof(info));qcrypto_wipe(salt,sizeof(salt));return rc;
}
int qboot_init(qboot_context *ctx,const uint8_t psk[32],const uint8_t aid[16],const uint8_t bid[16],uint32_t limit){
    if(!ctx)return -1;
    qboot_abort(ctx);
    if(!psk||!aid||!bid||!nonzero(psk,32)||!nonzero(aid,16)||!nonzero(bid,16)||same(aid,bid,16)||!limit||limit>QAS_MAX_PACKETS)return -1;
    memcpy(ctx->psk,psk,32);memcpy(ctx->aid,aid,16);memcpy(ctx->bid,bid,16);ctx->limit=limit;ctx->state=QB_NEW;return 0;
}
int qboot_server_hello(qboot_context *ctx,const uint8_t *ch,size_t n,const uint8_t nonce[32],uint8_t reply[105]){
    uint8_t expected[32],all[210];
    if(!ctx||ctx->state!=QB_NEW||!ch||n!=105||!nonce||!reply)return fail(ctx);
    if(memcmp(ch,"QBH1\x01",5)||tag(ctx->psk,"client-hello",ch,73,expected)||!same(expected,ch+73,32))return fail(ctx);
    if(!same(ch+5,ctx->aid,16)||!same(ch+21,ctx->bid,16)||!nonzero(ch+37,32)||!nonzero(nonce,32))return fail(ctx);
    uint32_t proposed=get32(ch+69);if(!proposed||proposed>QAS_MAX_PACKETS)return fail(ctx);
    ctx->chosen=proposed<ctx->limit?proposed:ctx->limit;memcpy(ctx->ch,ch,105);memcpy(ctx->na,ch+37,32);memcpy(ctx->nb,nonce,32);
    memcpy(ctx->sh,"QBH1\x02",5);if(qcrypto_sha256(ch,105,ctx->sh+5))return fail(ctx);
    memcpy(ctx->sh+37,nonce,32);put32(ctx->sh+69,ctx->chosen);
    if(tag(ctx->psk,"server-hello",ctx->sh,73,ctx->sh+73))return fail(ctx);
    memcpy(all,ctx->ch,105);memcpy(all+105,ctx->sh,105);
    if(qcrypto_sha256(all,sizeof(all),ctx->transcript)||derive(ctx,"sid",ctx->sid,16)||derive(ctx,"alice-to-bob",ctx->ab,16)||
       derive(ctx,"bob-to-alice",ctx->ba,16)||derive(ctx,"client-finished",ctx->cf,32)||derive(ctx,"server-finished",ctx->sf,32))return fail(ctx);
    memcpy(reply,ctx->sh,105);ctx->state=QB_WAIT;return 0;
}
int qboot_server_finished(qboot_context *ctx,const uint8_t *cf,size_t n,uint8_t reply[69]){
    uint8_t expected[32];
    if(!ctx||ctx->state!=QB_WAIT||!cf||n!=69||!reply)return fail(ctx);
    if(memcmp(cf,"QBH1\x03",5)||tag(ctx->cf,"client-finished",cf,37,expected)||!same(expected,cf+37,32)||!same(cf+5,ctx->transcript,32))return fail(ctx);
    memcpy(reply,"QBH1\x04",5);memcpy(reply+5,ctx->transcript,32);
    if(tag(ctx->sf,"server-finished",reply,37,reply+37))return fail(ctx);
    qcrypto_wipe(ctx->psk,32);qcrypto_wipe(ctx->cf,32);qcrypto_wipe(ctx->sf,32);ctx->state=QB_ESTABLISHED;return 0;
}
int qboot_take_session(qboot_context *ctx,qas_context *session){
    if(!session)return fail(ctx);
    if(!ctx||ctx->state!=QB_ESTABLISHED)return fail(ctx);
    qas_reset(session);
    int rc=qas_open(session,QAS_BOB,ctx->sid,ctx->ab,ctx->ba,ctx->chosen);
    qboot_abort(ctx);ctx->state=QB_CONSUMED;return rc==QAS_OK?0:-1;
}
