#include <stdlib.h>
#include "../../../firmware/zc702_uart/qas2_bootstrap.h"
void *qb_new(void){return calloc(1,sizeof(qboot_context));}
void qb_delete(void *p){if(p){qboot_abort(p);free(p);}}
