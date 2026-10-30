#include "auth_session.h"
#include "../crypto/siphash.h"
#include <string.h>

static void put32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static uint32_t get32(const uint8_t *p){uint32_t v=0;for(unsigned i=0;i<4;i++)v|=(uint32_t)p[i]<<(8*i);return v;}
static bool zero16(const uint8_t *p){uint8_t v=0;for(unsigned i=0;i<16;i++)v|=p[i];return v==0;}
static bool equal(const uint8_t *a,const uint8_t *b,unsigned n){
    uint8_t difference=0;for(unsigned i=0;i<n;i++)difference|=(uint8_t)(a[i]^b[i]);return difference==0;
}
void qas_reset(qas_context *ctx){
    if(ctx){volatile uint8_t *p=(volatile uint8_t*)ctx;for(unsigned i=0;i<sizeof(*ctx);i++)p[i]=0;}
}
qas_status qas_open(qas_context *ctx,qas_role role,const uint8_t sid[16],
                    const uint8_t ab[16],const uint8_t ba[16],uint32_t limit){
    if(!ctx||!sid||!ab||!ba)return QAS_ARGUMENT;
    if(ctx->active)return QAS_ARGUMENT;
    if((role!=QAS_ALICE&&role!=QAS_BOB)||!limit||limit>QAS_MAX_PACKETS||
       zero16(sid)||zero16(ab)||zero16(ba)||equal(ab,ba,16))return QAS_ARGUMENT;
    qas_reset(ctx);memcpy(ctx->sid,sid,16);
    memcpy(ctx->tx_key,role==QAS_ALICE?ab:ba,16);memcpy(ctx->rx_key,role==QAS_ALICE?ba:ab,16);
    ctx->tx_direction=(uint8_t)role;ctx->tx_next=1;ctx->limit=limit;ctx->active=true;
    return QAS_OK;
}
qas_status qas_wrap(qas_context *ctx,uint16_t opcode,const uint8_t *payload,
                    uint32_t length,uint8_t *frame,uint32_t capacity,uint32_t *written){
    if(written)*written=0;
    if(!ctx||!frame||!written||(length&&!payload)||length>QAS_MAX_PAYLOAD)return QAS_ARGUMENT;
    if(!ctx->active)return QAS_CLOSED;
    if(ctx->tx_used>=ctx->limit||ctx->tx_next==UINT32_MAX)return QAS_EXHAUSTED;
    if(capacity<QAS_HEADER_BYTES+length+QAS_TAG_BYTES)return QAS_CAPACITY;
    /* Move data first to support an in-place frame buffer without header loss. */
    if(length)memmove(frame+QAS_HEADER_BYTES,payload,length);
    memcpy(frame,"QAS2",4);frame[4]=2;frame[5]=ctx->tx_direction;
    frame[6]=(uint8_t)opcode;frame[7]=(uint8_t)(opcode>>8);
    memcpy(frame+8,ctx->sid,16);put32(frame+24,ctx->tx_next);put32(frame+28,length);
    if(siphash(frame,QAS_HEADER_BYTES+length,ctx->tx_key,frame+QAS_HEADER_BYTES+length,QAS_TAG_BYTES))return QAS_ARGUMENT;
    ctx->tx_next++;ctx->tx_used++;*written=QAS_HEADER_BYTES+length+QAS_TAG_BYTES;
    return QAS_OK;
}
qas_status qas_unwrap(qas_context *ctx,const uint8_t *frame,uint32_t length,
                      uint16_t *opcode,const uint8_t **payload,uint32_t *payload_length){
    if(opcode)*opcode=0;
    if(payload)*payload=NULL;
    if(payload_length)*payload_length=0;
    if(!ctx||!frame||!opcode||!payload||!payload_length)return QAS_ARGUMENT;
    if(!ctx->active)return QAS_CLOSED;
    if(length<QAS_HEADER_BYTES+QAS_TAG_BYTES||memcmp(frame,"QAS2",4)||frame[4]!=2)return QAS_FORMAT;
    uint32_t bytes=get32(frame+28),seq=get32(frame+24);
    if(bytes>QAS_MAX_PAYLOAD||length!=QAS_HEADER_BYTES+bytes+QAS_TAG_BYTES)return QAS_FORMAT;
    if(!equal(frame+8,ctx->sid,16))return QAS_SESSION;
    if(frame[5]!=(uint8_t)(ctx->tx_direction^1u))return QAS_DIRECTION;
    if(!seq||seq<=ctx->rx_last)return QAS_REPLAY;
    if(ctx->rx_checks>=ctx->limit)return QAS_EXHAUSTED;
    ctx->rx_checks++;uint8_t expected[QAS_TAG_BYTES];
    if(siphash(frame,QAS_HEADER_BYTES+bytes,ctx->rx_key,expected,QAS_TAG_BYTES))return QAS_ARGUMENT;
    if(!equal(expected,frame+QAS_HEADER_BYTES+bytes,QAS_TAG_BYTES))return QAS_BAD_TAG;
    ctx->rx_last=seq;*opcode=(uint16_t)((uint16_t)frame[6]|((uint16_t)frame[7]<<8));
    *payload=frame+QAS_HEADER_BYTES;*payload_length=bytes;return QAS_OK;
}
