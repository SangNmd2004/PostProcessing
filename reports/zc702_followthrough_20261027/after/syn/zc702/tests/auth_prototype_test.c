/* Host regression tests. Includes the exact prototype implementation so its
 * fixed-eight-byte SipHash helper can be compared with an independent reference.
 * No successful result here constitutes protocol security certification. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../../firmware/zc702_uart/auth_channel.c"
#include "siphash.h"

static unsigned checks;
#define REQUIRE(c) do {checks++; if(!(c)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#c);exit(1);}}while(0)
static uint64_t random_state=UINT64_C(0x7132a79432652def);
static uint64_t next_word(void){
    random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;
    return random_state;
}
static void little_endian(uint8_t *out,uint64_t value){
    for(unsigned i=0;i<8;i++)out[i]=(uint8_t)(value>>(8*i));
}

int main(void){
    REQUIRE(siphash24_64(UINT64_C(0x0706050403020100),UINT64_C(0x0f0e0d0c0b0a0908),
                        UINT64_C(0x0706050403020100))==UINT64_C(0x93f5f5799a932462));
    for(unsigned i=0;i<4096;i++){
        uint64_t k0=next_word(),k1=next_word(),message=next_word(),expected=0;
        uint8_t key[16],input[8],answer[8];
        little_endian(key,k0);little_endian(key+8,k1);little_endian(input,message);
        REQUIRE(siphash(input,8,key,answer,8)==0);
        for(unsigned j=0;j<8;j++)expected|=(uint64_t)answer[j]<<(8*j);
        REQUIRE(siphash24_64(k0,k1,message)==expected);
    }
    const unsigned lengths[]={0,1,7,8,9,64,AUTH_MAX_PAYLOAD};
    uint8_t payload[AUTH_MAX_PAYLOAD],packet[AUTH_MAX_PAYLOAD+sizeof(auth_header_t)];
    for(unsigned i=0;i<sizeof(payload);i++)payload[i]=(uint8_t)(i*31+7);
    for(unsigned i=0;i<sizeof(lengths)/sizeof(lengths[0]);i++){
        auth_context_t tx,rx,fresh;
        auth_channel_init(&tx,UINT64_C(0x987654321abcdef),UINT64_C(0x123456789abcdef));
        auth_channel_init(&rx,tx.hash_key,tx.psk_seed);fresh=rx;
        tx.tx_seq=0;uint32_t size=0,length=0;uint16_t type=99;const uint8_t *out=NULL;
        REQUIRE(auth_channel_wrap(&tx,0,payload,lengths[i],packet,&size)==0);
        REQUIRE(size==sizeof(auth_header_t)+lengths[i]);
        REQUIRE(auth_channel_unwrap_and_verify(&rx,packet,size,&type,&out,&length)==AUTH_OK);
        REQUIRE(type==0 && length==lengths[i] && memcmp(out,payload,length)==0);
        REQUIRE(auth_channel_unwrap_and_verify(&rx,packet,size,&type,&out,&length)==AUTH_ERR_REPLAY_SEQ);
        packet[12]^=1; /* Corrupt tag, including for an empty payload. */
        REQUIRE(auth_channel_unwrap_and_verify(&fresh,packet,size,&type,&out,&length)==AUTH_ERR_TAG_MISMATCH);
        REQUIRE(!fresh.has_rx_any);packet[12]^=1;
        REQUIRE(auth_channel_unwrap_and_verify(&fresh,packet,size-1,&type,&out,&length)==AUTH_ERR_PAYLOAD_LEN);
        REQUIRE(auth_channel_unwrap_and_verify(&fresh,packet,size,&type,&out,&length)==AUTH_OK);
    }
    auth_context_t invalid;uint32_t size=123;
    auth_channel_init(&invalid,0,1);
    REQUIRE(auth_channel_wrap(&invalid,0,NULL,0,packet,&size)==AUTH_ERR_LOCKOUT);
    auth_channel_init(&invalid,1,0);
    REQUIRE(auth_channel_wrap(&invalid,0,NULL,0,packet,&size)==AUTH_ERR_LOCKOUT);
    auth_channel_init(&invalid,1,2);
    REQUIRE(auth_channel_wrap(&invalid,0,NULL,1,packet,&size)==-1);
    invalid.tx_seq=UINT32_MAX;
    REQUIRE(auth_channel_wrap(&invalid,0,NULL,0,packet,&size)==AUTH_ERR_LOCKOUT);
    REQUIRE(invalid.tx_seq==UINT32_MAX && invalid.locked_out);
    REQUIRE(auth_channel_calc_epsilon_auth(&invalid)==1.0);
    printf("AUTH_PROTOTYPE_HOST_PASS checks=%u reference_pairs=4096 scope=algorithm_and_packet_regression_only\n",checks);
    return 0;
}
