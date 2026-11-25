#ifndef QKD_PACED_QUEUE_H
#define QKD_PACED_QUEUE_H
#include <stdint.h>
typedef struct {uint32_t ids[128],head,tail,count,capacity;} paced_queue_t;
static int paced_queue_init(paced_queue_t *q,uint32_t capacity){
    if(!q||!capacity||capacity>128)return -1;
    q->head=q->tail=q->count=0;q->capacity=capacity;return 0;
}
static int paced_queue_push(paced_queue_t *q,uint32_t id){
    if(q->count==q->capacity)return -1;
    q->ids[q->tail]=id;q->tail=(q->tail+1u)%128u;q->count++;return 0;
}
static int paced_queue_pop(paced_queue_t *q,uint32_t *id){
    if(!q->count)return -1;
    *id=q->ids[q->head];q->head=(q->head+1u)%128u;q->count--;return 0;
}
static int paced_safe_to_prepare(const uint32_t *stages,uint32_t contexts){
    if(!contexts||contexts>4)return 0;
    for(uint32_t i=0;i<contexts;i++)if(stages[i]==2u)return 0;
    return 1;
}
#endif
