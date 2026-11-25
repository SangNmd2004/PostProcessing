/* PUBLIC-FIXTURE LAB ONLY. QAS2 has MAC integrity, no confidentiality.
 * Baseline helpers are included through a private build overlay. */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "auth_session.h"
#include "../crypto/qcrypto.h"
static char secure_text[16000];
static uint32_t secure_text_n,secure_dispatch_count;
static int secure_overflow,secure_capture,secure_health=1;
static int secure_printf(const char *format,...){
    if(!secure_capture)return 0;
    if(secure_overflow)return -1;
    va_list ap;va_start(ap,format);
    int n=vsnprintf(secure_text+secure_text_n,sizeof(secure_text)-secure_text_n,format,ap);va_end(ap);
    if(n<0||(unsigned)n>=sizeof(secure_text)-secure_text_n){secure_overflow=1;return -1;}
    secure_text_n+=(uint32_t)n;return n;
}
#define xil_printf secure_printf
#define main unused_baseline_service_main
#include "secure_service_overlay.h"
#undef main
#undef xil_printf
static uint32_t secure_request[MAX_WORDS];
static uint32_t secure_time;

/* Stop every DMA channel before touching buffers after a hardware error.
 * A failed reset latches health=0, so application dispatch stays closed. */
static void secure_lifecycle_clear(void){
    wr(QKD,0x04u,2u);
    int rc=dma_reset(DMA_CH);rc|=dma_reset(DMA_SYN);
    rc|=dma_reset(DMA_PA);rc|=dma_reset(DMA_SEED);
    if(rc){secure_health=0;return;}
    functional_active=0;functional_key_valid=0;secure_bound=0;secure_time=0;
    ks_wipe(key_rx,sizeof(key_rx));ks_wipe(functional_x,sizeof(functional_x));
    ks_wipe(functional_seed,sizeof(functional_seed));ks_wipe(pa_rx,sizeof(pa_rx));
    ks_wipe(channel_data,sizeof(channel_data));ks_wipe(syndrome_data,sizeof(syndrome_data));
    ks_wipe(expected_key,sizeof(expected_key));ks_wipe(secure_bound_meta,sizeof(secure_bound_meta));
    secure_capture=1;secure_text_n=0;secure_overflow=0;
    frame[0]=61;rc=key_stream_command(1,0);
    secure_capture=0;secure_text_n=0;
    ks_wipe(frame,sizeof(frame));ks_wipe(secure_request,sizeof(secure_request));
    if(rc)secure_health=0;
}
static int secure_metadata(const uint32_t *m){
    if(m[1]>2765u||m[2]>2765u||m[3]>2765u||m[1]+m[2]+m[3]!=2765u)return 0;
    for(unsigned k=0;k<3;k++)if(!m[4+k]||m[4+k]>1000000000u||m[7+k]>m[4+k])return 0;
    return m[10]>=secure_time;
}
static int secure_load_valid(const uint32_t *w,uint32_t n){
    const uint32_t sizes[4]={48,32,24,16};
    if(n<5||functional_active||functional_key_valid||secure_bound||ks_pending||ks_out_bits)return 0;
    if(w[3]!=sizes[w[1]&3u]||w[4]>307u||n!=197u+w[3]+w[4])return 0;
    for(uint32_t i=197u+w[3];i<n;i++)if((w[i]&0xfffe0000u)||(w[i]&0xffffu)>=3072u)return 0;
    return 1;
}
/* Pure application preflight. Transport checks may consume the QAS2 MAC-check
 * budget; malformed/replayed frames never consume the verification-tag budget. */
static int secure_preflight(uint32_t *w,uint32_t n){
    uint32_t op=w[0];
    if(op==80u){
        if(n<16u||w[1]!=ks_next_id||ks_next_id==UINT32_MAX||!secure_metadata(w+1))return 0;
        uint32_t load[MAX_WORDS];load[0]=10;memcpy(load+1,w+12,(n-12u)*4u);
        return secure_load_valid(load,n-11u);
    }
    if(op==10u)return secure_load_valid(w,n);
    if(op==11u)return n==1u&&functional_active;
    if(op==12u){
        if(n<2u||!functional_active||w[1]>307u||n!=2u+w[1]||functional_revealed+w[1]>307u)return 0;
        for(uint32_t i=2;i<n;i++)if((w[i]&0xfffe0000u)||(w[i]&0xffffu)>=3072u)return 0;
        return 1;
    }
    if(op==14u)return n==1u&&functional_key_valid; /* Existing lab debug only. */
    if(op==20u){
        if(n!=583u||!functional_key_valid||secure_bound||w[1]!=functional_code)return 0;
        for(unsigned k=0;k<307;k++)if(w[2+k]!=qkd_punct_pos[functional_code][k])return 0;
        return 1;
    }
    if(op==60u)return n==134u&&secure_bound&&functional_key_valid&&!functional_active&&
        !ks_pending&&!ks_out_bits&&ks_bits<=KS_MAX_BITS-2765u&&
        !memcmp(w+1,secure_bound_meta,sizeof(secure_bound_meta));
    if(op==61u||op==81u||op==67u||op==69u||op==73u||op==82u)return n==1u;
    if(op==62u)return n==2u&&!functional_active&&!functional_key_valid&&!secure_bound&&
        !ks_pending&&!ks_out_bits&&w[1]>=secure_time;
    if(op==63u)return n>=5u&&ks_pending&&w[1]==ks_seed_words&&w[2]==ks_seed_loaded&&
        w[3]==n-4u&&ks_seed_loaded<=ks_seed_words&&w[3]<=ks_seed_words-ks_seed_loaded;
    if(op==64u)return n==1u&&ks_pending&&ks_seed_loaded==ks_seed_words&&!ks_out_bits;
    if(op==65u)return n==3u&&ks_out_bits&&w[1]<=ks_out_bits/64u&&w[2]>0u&&w[2]<=128u&&w[2]<=ks_out_bits/64u-w[1];
    if(op==66u)return n==1u&&ks_out_bits&&!ks_pending;
    if(op==72u)return n==2u&&!functional_active&&w[1]>=verification_used&&w[1]<=verification_limit;
    return 0; /* Includes raw accumulator metadata ops 30..33 and debug op68. */
}
static int secure_dispatch(qas_context *session,const uint8_t *packet,uint32_t packet_n,
                           uint8_t *response,uint32_t capacity,uint32_t *written){
    uint16_t opcode;const uint8_t *payload;uint32_t bytes;
    *written=0;
    int rc=qas_unwrap(session,packet,packet_n,&opcode,&payload,&bytes);
    if(rc)return rc;
    /* Reserve worst-case response space/budget before application side effects. */
    if(capacity<sizeof(secure_text)+QAS_HEADER_BYTES+QAS_TAG_BYTES)return QAS_CAPACITY;
    if(session->tx_used>=session->limit||session->tx_next==UINT32_MAX)return QAS_EXHAUSTED;
    secure_capture=1;secure_overflow=0;secure_text_n=0;
    uint32_t n=bytes/4u;
    if(bytes<=sizeof(secure_request)&&bytes)memcpy(secure_request,payload,bytes);
    if(!secure_health||opcode!=0x100u||!bytes||bytes%4u||bytes>sizeof(secure_request)||!secure_preflight(secure_request,n)){
        secure_printf("QKD_SECURE_REJECT seq=%u reason=POLICY\r\n",session->rx_last);
    }else{
        uint32_t op=secure_request[0];secure_dispatch_count++;
        memcpy(frame,secure_request,bytes);
        if(op==80u){
            memcpy(secure_bound_meta,frame+1,sizeof(secure_bound_meta));
            memmove(frame+1,frame+12,(n-12u)*4u);frame[0]=10;
            rc=functional_command(n-11u,session->rx_last);
            if(!rc){secure_bound=1;secure_time=secure_bound_meta[10];}
        }else if(op==61u||op==81u){
            uint32_t next=ks_next_id+(secure_bound?1u:0u),used=verification_used,at=secure_time;
            secure_lifecycle_clear();ks_next_id=next;secure_time=at;
            secure_capture=1;
            secure_printf("QKD_SECURE_ABORT seq=%u next_id=%u used=%u\r\n",session->rx_last,next,used);
            rc=secure_health?0:-1;
        }else if(op==82u){
            uint8_t digest[32];rc=qcrypto_sha256((const uint8_t*)ks_key,(ks_bits+7u)/8u,digest);
            secure_printf("QKD_SECURE_BUFFER seq=%u bits=%u sha256=",session->rx_last,ks_bits);
            for(unsigned i=0;i<32;i++)secure_printf("%02x",digest[i]);
            secure_printf("\r\n");
        }else{
            if(op==62u)secure_time=frame[1];
            rc=functional_command(n,session->rx_last);
        }
        if(rc||secure_overflow){
            secure_lifecycle_clear();secure_health=0;secure_capture=1;secure_text_n=0;secure_overflow=0;
            secure_printf("QKD_SECURE_FAULT seq=%u health=0\r\n",session->rx_last);
        }
    }
    secure_capture=0;
    return qas_wrap(session,0x8100u,(const uint8_t*)secure_text,secure_text_n,response,capacity,written);
}
