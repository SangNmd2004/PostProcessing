/* Included after the existing smoke helpers in a SEPARATE test translation
 * unit. Baseline sources/binary are not edited. Only allowlisted functional
 * commands can be dispatched, after successful QAS2 authentication. */
#include <stdarg.h>
#include <stdio.h>
#include "auth_session.h"
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
#include "service.h"
#undef main
#undef xil_printf
static void secure_lifecycle_clear(void){
    secure_capture=1;secure_text_n=0;secure_overflow=0;
    frame[0]=13;int rc=functional_command(1,0); /* Stop active decode, clear key-valid. */
    frame[0]=61;rc|=functional_command(1,0); /* Wipe stream staging, never refund tag cap. */
    secure_capture=0;secure_text_n=0;
    if(rc)secure_health=0;
}
static int secure_dispatch(qas_context *session,const uint8_t *packet,uint32_t packet_n,
                           uint8_t *response,uint32_t capacity,uint32_t *written){
    uint16_t opcode;const uint8_t *payload;uint32_t n;
    *written=0;
    int rc=qas_unwrap(session,packet,packet_n,&opcode,&payload,&n);
    if(rc)return rc;
    if(!secure_health||opcode!=0x100u||!n||(n%4)||n>sizeof(frame))return -90;
    uint32_t op;memcpy(&op,payload,4);
    if(op!=10&&op!=11&&op!=12&&op!=14&&op!=20&&op!=73)return -91;
    memcpy(frame,payload,n);secure_capture=1;secure_overflow=0;secure_text_n=0;
    secure_dispatch_count++;
    rc=functional_command(n/4,session->rx_last);
    secure_capture=0;
    if(rc||secure_overflow){secure_lifecycle_clear();return -92;}
    return qas_wrap(session,0x8100u,(const uint8_t*)secure_text,secure_text_n,response,capacity,written);
}
