#include <assert.h>
#include <stdio.h>
#include "paced_queue.h"
int main(void){
    paced_queue_t q;uint32_t id;
    for(unsigned mask=0;mask<256;mask++){
        uint32_t states[4];int active=0;
        for(unsigned i=0;i<4;i++){states[i]=(mask>>(2*i))&3u;active|=states[i]==2u;}
        assert(paced_safe_to_prepare(states,4)==!active);
    }
    assert(paced_queue_init(&q,0));assert(paced_queue_init(&q,129));assert(paced_queue_init(NULL,1));
    for(unsigned cap=1;cap<=128;cap++){
        assert(!paced_queue_init(&q,cap));
        for(unsigned round=0;round<100;round++){
            assert(paced_queue_pop(&q,&id));
            for(unsigned i=0;i<cap;i++)assert(!paced_queue_push(&q,round*128+i));
            assert(paced_queue_push(&q,999999));assert(q.count==cap);
            for(unsigned i=0;i<cap;i++){assert(!paced_queue_pop(&q,&id));assert(id==round*128+i);}
            assert(q.count==0);
        }
    }
    puts("PACED_QUEUE_C_PASS capacities=1..128 wrap_rounds=100 FIFO/drop/empty and 256 reveal-safety states");return 0;
}
