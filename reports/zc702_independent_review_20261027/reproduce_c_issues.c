#include <stdio.h>
#include <stddef.h>
#include "auth_channel.h"
#include "event_scheduler.h"
#include "session_persistence.h"

int main(void) {
    persistent_session_t original, restored;
    uint32_t uuid[4]={1,2,3,4};
    session_persist_init(&original,uuid,1,18446);
    int restore=session_persist_restore(&restored,&original);
    printf("persistence_fresh_restore_rc=%d sizeof=%llu crc_offset=%llu\n",restore,
           (unsigned long long)sizeof(original),(unsigned long long)offsetof(persistent_session_t,descriptor_crc));
    event_scheduler_t s; sched_event_t event;
    event_scheduler_init(&s);
    int failed=-1;
    for(int i=0;i<40;i++) {
        int a=event_scheduler_post_from_isr(&s,EVT_DMA_CH_DONE,0,0);
        int b=event_scheduler_post_from_isr(&s,EVT_QKD_DECODE_DONE,1,0);
        if(!a||!b){failed=i;break;}
        if(!event_scheduler_poll(&s,EVT_QKD_DECODE_DONE,&event))return 5;
        if(!event_scheduler_poll(&s,EVT_DMA_CH_DONE,&event))return 6;
    }
    printf("selective_queue_first_failed_round=%d head=%u tail=%u\n",failed,s.head,s.tail);
    auth_context_t tx,rx; unsigned char buffer[100];uint32_t size=0,length=0;
    const uint8_t *payload;uint16_t type;
    auth_channel_init(&tx,0xabcdef,0x12345678);auth_channel_init(&rx,0xabcdef,0x12345678);
    tx.tx_seq=0;
    auth_channel_wrap(&tx,0,(const uint8_t*)"x",1,buffer,&size);
    int first=auth_channel_unwrap_and_verify(&rx,buffer,size,&type,&payload,&length);
    int replay=auth_channel_unwrap_and_verify(&rx,buffer,size,&type,&payload,&length);
    printf("seq0_first_rc=%d seq0_replay_rc=%d\n",first,replay);
    auth_channel_init(&tx,0x9e3779b97f4a7c15ULL,0x0123456789abcdefULL);
    printf("empty_type0_tag=%016llx\n",(unsigned long long)auth_channel_compute_mac(&tx,(const uint8_t*)"",0,1,0));
    return 0;
}
