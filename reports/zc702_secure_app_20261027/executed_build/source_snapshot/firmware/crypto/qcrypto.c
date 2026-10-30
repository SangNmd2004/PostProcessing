#include "qcrypto.h"
#include "rfc6234/sha.h"
#include <string.h>
#include <limits.h>
void qcrypto_wipe(void *p,size_t n){volatile uint8_t *v=p;while(n--)*v++=0;}
int qcrypto_sha256(const uint8_t *data,size_t n,uint8_t out[32]){
    SHA256Context ctx;int rc=-1;
    if(!out||(n&&!data)||n>UINT_MAX)return -1;
    if(!SHA256Reset(&ctx)&&!SHA256Input(&ctx,data,(unsigned)n)&&!SHA256Result(&ctx,out))rc=0;
    qcrypto_wipe(&ctx,sizeof(ctx));return rc;
}
int qcrypto_hmac(const uint8_t *key,size_t key_n,const uint8_t *data,size_t n,uint8_t out[32]){
    uint8_t k[64]={0},pad[64],inner[32];SHA256Context ctx;int rc=-1;
    if(!out||(key_n&&!key)||(n&&!data)||n>UINT_MAX||key_n>UINT_MAX)return -1;
    if(key_n>64){if(qcrypto_sha256(key,key_n,k))goto done;}else if(key_n)memcpy(k,key,key_n);
    for(unsigned i=0;i<64;i++)pad[i]=(uint8_t)(k[i]^0x36);
    if(SHA256Reset(&ctx)||SHA256Input(&ctx,pad,64)||SHA256Input(&ctx,data,(unsigned)n)||SHA256Result(&ctx,inner))goto done;
    for(unsigned i=0;i<64;i++)pad[i]=(uint8_t)(k[i]^0x5c);
    if(SHA256Reset(&ctx)||SHA256Input(&ctx,pad,64)||SHA256Input(&ctx,inner,32)||SHA256Result(&ctx,out))goto done;
    rc=0;
done:qcrypto_wipe(k,sizeof(k));qcrypto_wipe(pad,sizeof(pad));qcrypto_wipe(inner,sizeof(inner));qcrypto_wipe(&ctx,sizeof(ctx));return rc;
}
int qcrypto_hkdf(const uint8_t *ikm,size_t ikm_n,const uint8_t *salt,size_t salt_n,
                 const uint8_t *info,size_t info_n,uint8_t *out,size_t out_n){
    uint8_t prk[32],t[32],input[161],zero[32]={0};size_t t_n=0,at=0;int rc=-1;
    if((ikm_n&&!ikm)||(salt_n&&!salt)||(info_n&&!info)||(out_n&&!out)||out_n>8160||info_n>128)return -1;
    if(!salt_n){salt=zero;salt_n=32;}
    if(qcrypto_hmac(salt,salt_n,ikm,ikm_n,prk))goto done;
    for(unsigned counter=1;at<out_n;counter++){
        if(t_n)memcpy(input,t,t_n);
        if(info_n)memcpy(input+t_n,info,info_n);
        input[t_n+info_n]=(uint8_t)counter;
        if(qcrypto_hmac(prk,32,input,t_n+info_n+1,t))goto done;
        size_t take=out_n-at<32?out_n-at:32;memcpy(out+at,t,take);at+=take;t_n=32;
    }
    rc=0;
done:if(rc&&out&&out_n)qcrypto_wipe(out,out_n);
    qcrypto_wipe(prk,sizeof(prk));qcrypto_wipe(t,sizeof(t));qcrypto_wipe(input,sizeof(input));return rc;
}
