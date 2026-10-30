/* LAB-ONLY firmware. Root PSK and peer IDs are PUBLIC FIXTURES. The plaintext
 * I/R commands allow provisioning/reset and are NOT a production dispatcher.
 * nonceB is supplied by the host fixture, NOT by a physical TRNG. */
#include "qas2_bootstrap.h"
#include "../crypto/qcrypto.h"
#include "xil_printf.h"
#include "xuartps_hw.h"
#include "xil_cache.h"
#include <string.h>
static qboot_context boot;
static qas_context data_session;
static uint8_t nonce[32],input[16424],reply[16424];
static char line[32860];
static int digit(char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
static int unhex(const char *text,uint8_t *out,size_t cap){
    size_t n=strlen(text);if(n%2||n/2>cap)return -1;
    for(size_t i=0;i<n/2;i++){int a=digit(text[2*i]),b=digit(text[2*i+1]);if(a<0||b<0)return -1;out[i]=(uint8_t)(a*16+b);}
    return (int)(n/2);
}
static void answer(int rc,const uint8_t *bytes,unsigned n){
    xil_printf("QB %d",rc);if(!rc&&n){xil_printf(" ");for(unsigned i=0;i<n;i++)xil_printf("%02x",bytes[i]);}xil_printf("\r\n");
}
static int kat(void){
    uint8_t key[22],out[42],wanted[42],salt[13],info[10];memset(key,0x0b,sizeof(key));
    if(unhex("b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",wanted,sizeof(wanted))!=32)return -1;
    if(qcrypto_hmac(key,20,(const uint8_t*)"Hi There",8,out)||memcmp(out,wanted,32))return -1;
    for(unsigned i=0;i<13;i++)salt[i]=(uint8_t)i;
    for(unsigned i=0;i<10;i++)info[i]=(uint8_t)(0xf0+i);
    if(unhex("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865",wanted,sizeof(wanted))!=42)return -1;
    return qcrypto_hkdf(key,22,salt,13,info,10,out,42)||memcmp(out,wanted,42)?-1:0;
}
int main(void){
    Xil_ICacheEnable();Xil_DCacheEnable();qas_reset(&data_session);qboot_abort(&boot);
    if(kat()){xil_printf("QB_READY kat=FAIL fixture=PUBLIC\r\n");return 1;}
    xil_printf("QB_READY kat=PASS fixture=PUBLIC\r\n");
    for(;;){
        unsigned used=0;int overflow=0;
        for(;;){char c=(char)XUartPs_RecvByte(0xe0001000u);if(c=='\r')continue;if(c=='\n')break;
            if(used+1<sizeof(line))line[used++]=c;else overflow=1;}
        line[used]=0;
        if(overflow){answer(-99,NULL,0);continue;}
        if(used==1&&line[0]=='R'){qboot_abort(&boot);qas_reset(&data_session);qcrypto_wipe(nonce,32);answer(0,NULL,0);continue;}
        if(used<2||line[1]!=' '){answer(-98,NULL,0);continue;}
        int n=unhex(line+2,input,sizeof(input));if(n<0){answer(-97,NULL,0);continue;}
        int rc=-96;unsigned count=0;
        if(line[0]=='I'){
            qboot_abort(&boot);qas_reset(&data_session);
            uint8_t psk[32],aid[16],bid[16];
            for(unsigned i=0;i<32;i++)psk[i]=(uint8_t)(i+1);
            for(unsigned i=0;i<16;i++){aid[i]=(uint8_t)(i+1);bid[i]=(uint8_t)(i+17);}
            if(n==32){memcpy(nonce,input,32);rc=qboot_init(&boot,psk,aid,bid,16);}
            qcrypto_wipe(psk,32);
        }else if(line[0]=='H'){
            qas_reset(&data_session);rc=qboot_server_hello(&boot,input,(size_t)n,nonce,reply);if(!rc)count=105;
        }else if(line[0]=='F'){
            rc=qboot_server_finished(&boot,input,(size_t)n,reply);
            if(!rc){rc=qboot_take_session(&boot,&data_session);if(!rc)count=69;}
            if(rc)qas_reset(&data_session);
        }else if(line[0]=='D'){
            uint16_t op;const uint8_t *payload;uint32_t bytes,written;
            rc=qas_unwrap(&data_session,input,(uint32_t)n,&op,&payload,&bytes);
            if(!rc){rc=qas_wrap(&data_session,(uint16_t)(op^0x8000),payload,bytes,reply,sizeof(reply),&written);if(!rc)count=written;}
        }
        answer(rc,reply,count);
    }
}
