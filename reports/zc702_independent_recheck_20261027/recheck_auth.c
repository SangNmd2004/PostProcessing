#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "../../firmware/zc702_uart/auth_channel.c"
#include "reference/siphash.h"
#include "../../firmware/zc702_uart/session_persistence.h"

int main(void) {
    uint8_t key[16],message[8],reference[8];uint64_t expected;
    for(int i=0;i<16;i++)key[i]=(uint8_t)i;
    for(int i=0;i<8;i++)message[i]=(uint8_t)i;
    siphash(message,8,key,reference,8);memcpy(&expected,reference,8);
    uint64_t actual=siphash24_64(0x0706050403020100ULL,0x0f0e0d0c0b0a0908ULL,0x0706050403020100ULL);
    printf("siphash_reference=%016llx project=%016llx equal=%d\n",(unsigned long long)expected,(unsigned long long)actual,expected==actual);
    persistent_session_t old,cold,working;
    uint32_t uuid[4]={1,2,3,4};
    session_persist_init(&old,uuid,1,18446);
    working=old;
    for(int i=0;i<10;i++)session_persist_charge_verification(&working,1);
    memset(&cold,0,sizeof(cold));
    int rc=session_persist_restore(&cold,&old);
    printf("cold_restore_old_snapshot_rc=%d used_after_restore=%u previous_used=%u\n",rc,cold.budget_used,working.budget_used);
    return 0;
}
