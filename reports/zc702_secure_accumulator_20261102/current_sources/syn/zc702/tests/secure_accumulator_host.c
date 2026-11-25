#include <assert.h>
#include "secure_accumulator_service.h"
static qas_context alice,bob;
static uint8_t packet[16424],response[16424];
static unsigned checks;
#define CHECK(x) do{assert(x);checks++;}while(0)
static void session(unsigned limit){
    uint8_t sid[16]={1},ab[16]={2},ba[16]={3};qas_reset(&alice);qas_reset(&bob);
    CHECK(!qas_open(&alice,QAS_ALICE,sid,ab,ba,limit));CHECK(!qas_open(&bob,QAS_BOB,sid,ab,ba,limit));
}
static uint32_t send(uint32_t *w,unsigned n,int reject){
    uint32_t pn,rn,bytes;uint16_t op;const uint8_t *payload;
    CHECK(!qas_wrap(&alice,0x100,(uint8_t*)w,n*4,packet,sizeof(packet),&pn));
    CHECK(!secure_dispatch(&bob,packet,pn,response,sizeof(response),&rn));
    CHECK(!qas_unwrap(&alice,response,rn,&op,&payload,&bytes));CHECK(op==0x8100);
    char text[16385];CHECK(bytes<sizeof(text));memcpy(text,payload,bytes);text[bytes]=0;
    CHECK((strstr(text,"QKD_SECURE_REJECT")!=NULL)==reject);
    return pn;
}
static void unchanged(uint32_t *w,unsigned n){
    unsigned d=host_dma,v=verification_used,k=ks_bits,id=ks_next_id,c=secure_dispatch_count,b=secure_bound;
    send(w,n,1);CHECK(d==host_dma&&v==verification_used&&k==ks_bits&&id==ks_next_id&&c==secure_dispatch_count&&b==(unsigned)secure_bound);
}
int main(void){
    secure_lifecycle_clear();session(10000);
    uint32_t w[1024]={80,0,2633,129,3,2607,135,4,0,0,0,0,3,44,16,0};
    unchanged(w,223); /* expected 224 words: missing input */
    w[1]=1;unchanged(w,224);w[1]=0;
    w[8]=2608;unchanged(w,224);w[8]=0;
    send(w,224,0);CHECK(secure_bound&&functional_active);
    uint32_t reveal[]={12,2,0,999999};unchanged(reveal,4); /* validate all before register writes */
    uint32_t run[]={11};send(run,1,0);
    uint32_t append[134]={60,0,2633,129,3,2607,135,4,0,0,0,0};append[132]=123;
    append[1]=1;unchanged(append,134);append[1]=0;
    append[2]--;unchanged(append,134);append[2]++;
    unchanged(append,133);append[134-1]=0;
    unsigned d=host_dma,v=verification_used,k=ks_bits;
    uint32_t pn,rn;CHECK(!qas_wrap(&alice,0x100,(uint8_t*)append,sizeof(append),packet,sizeof(packet),&pn));packet[pn-1]^=1;
    CHECK(secure_dispatch(&bob,packet,pn,response,sizeof(response),&rn)==QAS_BAD_TAG);CHECK(d==host_dma&&v==verification_used&&k==ks_bits);
    packet[pn-1]^=1;CHECK(!secure_dispatch(&bob,packet,pn,response,sizeof(response),&rn));
    {uint16_t op;const uint8_t *p;uint32_t n;CHECK(!qas_unwrap(&alice,response,rn,&op,&p,&n));}
    CHECK(ks_bits==2765&&verification_used==1&&!secure_bound&&ks_next_id==1);
    d=host_dma;CHECK(secure_dispatch(&bob,packet,pn,response,sizeof(response),&rn)==QAS_REPLAY);CHECK(d==host_dma&&verification_used==1);
    unchanged(append,134);
    /* Real C capacity boundary, without transferring 16 Mbit over a fake UART. */
    w[1]=1;w[11]=1;send(w,224,0);send(run,1,0);append[1]=1;append[11]=1;
    ks_bits=KS_MAX_BITS-2764;unchanged(append,134);ks_bits=2765;
    append[132]^=1;send(append,134,0);CHECK(verification_used==2&&ks_bits==2765&&ks_next_id==2&&!functional_key_valid);
    uint32_t abort[]={81};send(abort,1,0);CHECK(ks_bits==0&&ks_next_id==2&&verification_used==2);
    for(unsigned i=0;i<KS_WORDS;i++)CHECK(!ks_key[i]&&!ks_work[i]);
    for(unsigned i=0;i<sizeof(ks_seed)/4;i++)CHECK(!ks_seed[i]);
    /* Real C split shift, prefix retirement and non-word-aligned tail. */
    ks_bits=123;ks_emit_bits=37;ks_ell=64;ks_pending=1;ks_seed_loaded=ks_seed_words=35;
    ks_acc.split=1;ks_acc.nk[0]=123;ks_acc.best_nk[0]=37;
    uint8_t original[123];for(unsigned i=0;i<123;i++){original[i]=(uint8_t)((i*7+i/3)&1);ks_key[i/32]|=(uint32_t)original[i]<<(i%32);}
    uint32_t emit[]={64};send(emit,1,0);CHECK(ks_bits==86&&ks_out_bits==64);
    for(unsigned i=0;i<86;i++)CHECK(((ks_key[i/32]>>(i%32))&1)==original[i+37]);
    CHECK((ks_key[2]>>22)==0);
    uint32_t read[]={65,0,129};unchanged(read,3);
    send(abort,1,0);
    /* A response cannot be lost because its buffer or TX budget was unavailable. */
    CHECK(!qas_wrap(&alice,0x100,(uint8_t*)w,224*4,packet,sizeof(packet),&pn));
    d=host_dma;CHECK(secure_dispatch(&bob,packet,pn,response,40,&rn)==QAS_CAPACITY);CHECK(d==host_dma);
    session(1);uint32_t query[]={67};send(query,1,0);
    /* Independent direction budget: exhaust Bob replies while RX remains live. */
    session(10);bob.tx_used=10;CHECK(!qas_wrap(&alice,0x100,(uint8_t*)w,224*4,packet,sizeof(packet),&pn));
    d=host_dma;CHECK(secure_dispatch(&bob,packet,pn,response,sizeof(response),&rn)==QAS_EXHAUSTED);CHECK(d==host_dma);
    /* DMA failure during PA: real handler failure wipes and latches closed. */
    session(100);ks_bits=64;ks_emit_bits=64;ks_ell=64;ks_pending=1;ks_seed_loaded=ks_seed_words=35;host_fail=1;
    send(emit,1,0);CHECK(!secure_health&&!ks_bits&&!ks_out_bits);host_fail=0;
    unchanged(w,224);secure_lifecycle_clear();CHECK(verification_used==2&&!secure_health);
    printf("SECURE_ACCUMULATOR_HOST_PASS checks=%u DMA_INSTRUMENTED_NOT_PL\n",checks);return 0;
}
