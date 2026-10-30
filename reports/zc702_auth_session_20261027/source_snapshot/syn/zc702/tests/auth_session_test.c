#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../../firmware/zc702_uart/auth_session.h"
#include "../../../firmware/crypto/siphash.h"
static unsigned checks;
#define REQUIRE(x) do{checks++;if(!(x)){fprintf(stderr,"FAIL line=%d expr=%s\n",__LINE__,#x);exit(1);}}while(0)
static const uint8_t sid[16]={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
static const uint8_t ab[16]={3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59};
static const uint8_t ba[16]={61,67,71,73,79,83,89,97,101,103,107,109,113,127,131,137};
static void pair(qas_context *a,qas_context *b,uint32_t limit){
    qas_reset(a);qas_reset(b);
    REQUIRE(qas_open(a,QAS_ALICE,sid,ab,ba,limit)==QAS_OK);
    REQUIRE(qas_open(b,QAS_BOB,sid,ab,ba,limit)==QAS_OK);
}
int main(void){
    uint8_t key[16],answer[8];for(unsigned i=0;i<16;i++)key[i]=(uint8_t)i;
    const uint8_t kat0[8]={0x31,0x0e,0x0e,0xdd,0x47,0xdb,0x6f,0x72};
    uint8_t empty=0;
    REQUIRE(siphash(&empty,0,key,answer,8)==0);REQUIRE(!memcmp(answer,kat0,8));
    uint8_t payload[QAS_MAX_PAYLOAD],frame[QAS_HEADER_BYTES+QAS_MAX_PAYLOAD+QAS_TAG_BYTES],saved[sizeof(frame)];
    for(unsigned i=0;i<sizeof(payload);i++)payload[i]=(uint8_t)(i*17+3);
    const unsigned sizes[]={0,1,7,8,9,31,32,255,QAS_MAX_PAYLOAD};
    qas_context a,b;uint32_t written,length;uint16_t opcode;const uint8_t *out;
    for(unsigned i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++){
        pair(&a,&b,100);
        REQUIRE(qas_wrap(&a,0x1234,payload,sizes[i],frame,sizeof(frame),&written)==QAS_OK);
        REQUIRE(written==QAS_HEADER_BYTES+sizes[i]+QAS_TAG_BYTES);
        REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_OK);
        REQUIRE(opcode==0x1234&&length==sizes[i]&&!memcmp(out,payload,length));
        REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_REPLAY);
        REQUIRE(opcode==0&&out==NULL&&length==0);
        REQUIRE(qas_wrap(&b,0xabcd,payload,sizes[i],frame,sizeof(frame),&written)==QAS_OK);
        REQUIRE(qas_unwrap(&a,frame,written,&opcode,&out,&length)==QAS_OK);
        REQUIRE(opcode==0xabcd&&length==sizes[i]);
    }
    pair(&a,&b,100);REQUIRE(qas_wrap(&a,0x1234,payload,64,frame,sizeof(frame),&written)==QAS_OK);
    memcpy(saved,frame,written);
    /* Every header, payload and tag byte is authenticated or structurally rejected. */
    for(unsigned i=0;i<written;i++){
        qas_reset(&b);REQUIRE(qas_open(&b,QAS_BOB,sid,ab,ba,100)==QAS_OK);
        memcpy(frame,saved,written);frame[i]^=1;
        out=payload;length=99;opcode=99;
        REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)!=QAS_OK);
        REQUIRE(!b.rx_last&&!out&&!length&&!opcode);
    }
    memcpy(frame,saved,written);
    pair(&a,&b,100);
    REQUIRE(qas_unwrap(&a,frame,written,&opcode,&out,&length)==QAS_DIRECTION);
    uint8_t other[16];memcpy(other,sid,16);other[15]^=1;
    qas_reset(&b);REQUIRE(qas_open(&b,QAS_BOB,other,ab,ba,100)==QAS_OK);
    REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_SESSION);
    qas_reset(&b);REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_CLOSED);
    for(unsigned i=0;i<sizeof(b);i++)REQUIRE(((uint8_t*)&b)[i]==0);
    pair(&a,&b,2);REQUIRE(qas_wrap(&a,7,payload,3,frame,sizeof(frame),&written)==QAS_OK);
    frame[written-1]^=1;
    REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_BAD_TAG);
    REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_BAD_TAG);
    REQUIRE(b.rx_checks==2&&b.rx_last==0);
    frame[written-1]^=1;
    REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_EXHAUSTED);
    REQUIRE(qas_wrap(&a,8,NULL,0,frame,sizeof(frame),&written)==QAS_OK);
    REQUIRE(qas_wrap(&a,9,NULL,0,frame,sizeof(frame),&written)==QAS_EXHAUSTED&&written==0);
    pair(&a,&b,100);
    REQUIRE(qas_wrap(&a,1,payload,1,frame,1,&written)==QAS_CAPACITY&&a.tx_next==1);
    REQUIRE(qas_wrap(&a,1,NULL,1,frame,sizeof(frame),&written)==QAS_ARGUMENT);
    uint8_t zero[16]={0};qas_reset(&b);
    REQUIRE(qas_open(&b,QAS_BOB,zero,ab,ba,100)==QAS_ARGUMENT);
    REQUIRE(qas_open(&b,QAS_BOB,sid,ab,ab,100)==QAS_ARGUMENT);
    REQUIRE(qas_open(&b,QAS_BOB,sid,zero,ba,100)==QAS_ARGUMENT);
    REQUIRE(qas_open(&b,QAS_BOB,sid,ab,ba,0)==QAS_ARGUMENT);
    REQUIRE(qas_open(&b,QAS_BOB,sid,ab,ba,QAS_MAX_PACKETS+1)==QAS_ARGUMENT);
    pair(&a,&b,100);
    memcpy(frame,payload,64);
    REQUIRE(qas_wrap(&a,0,frame,64,frame,sizeof(frame),&written)==QAS_OK);
    REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_OK&&!memcmp(out,payload,64));
    /* Explicit negative scope: a trusted caller that reuses the OLD SID/keys
     * after RAM reset can still permit replay. No durable anchor is present. */
    qas_reset(&b);REQUIRE(qas_open(&b,QAS_BOB,sid,ab,ba,100)==QAS_OK);
    REQUIRE(qas_unwrap(&b,frame,written,&opcode,&out,&length)==QAS_OK);
    printf("KNOWN_LIMITATION trusted_reopen_with_old_SID_keys_can_accept_old_frame=1\n");
    printf("AUTH_SESSION_HOST_PASS checks=%u tampered_bytes=104 sizes=9 scope=volatile_session_only\n",checks);
    return 0;
}
