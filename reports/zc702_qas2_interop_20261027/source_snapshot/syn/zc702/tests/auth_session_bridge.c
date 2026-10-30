/* Test-only opaque ctypes bridge. No transport or board access. */
#include <stdlib.h>
#include "../../../firmware/zc702_uart/auth_session.h"
void *bridge_new(void){return calloc(1,sizeof(qas_context));}
void bridge_delete(void *ctx){if(ctx){qas_reset(ctx);free(ctx);}}
int bridge_open(void *ctx,int role,const uint8_t *sid,const uint8_t *ab,const uint8_t *ba,uint32_t limit){
    return qas_open(ctx,(qas_role)role,sid,ab,ba,limit);
}
void bridge_reset(void *ctx){qas_reset(ctx);}
int bridge_wrap(void *ctx,uint16_t op,const uint8_t *payload,uint32_t length,uint8_t *out,uint32_t cap,uint32_t *written){
    return qas_wrap(ctx,op,payload,length,out,cap,written);
}
int bridge_unwrap(void *ctx,const uint8_t *frame,uint32_t length,uint16_t *opcode,uint8_t *out,uint32_t *written){
    const uint8_t *payload=NULL;
    int rc=qas_unwrap(ctx,frame,length,opcode,&payload,written);
    if(rc==QAS_OK){for(uint32_t i=0;i<*written;i++)out[i]=payload[i];}
    return rc;
}
uint32_t bridge_last(void *ctx){return ((qas_context*)ctx)->rx_last;}
uint32_t bridge_checks(void *ctx){return ((qas_context*)ctx)->rx_checks;}
