#ifndef QKD_QAS2_BOOTSTRAP_H
#define QKD_QAS2_BOOTSTRAP_H
#include <stddef.h>
#include <stdint.h>
#include "auth_session.h"
/* Bob-side prototype; entropy/trusted root provisioning supplied by caller.
 * Not standardized, forward secret, or persistent. qboot_init requires a new
 * connection; never invoke it from an unauthenticated application command. */
typedef struct {
    uint8_t psk[32],aid[16],bid[16],na[32],nb[32],ch[105],sh[105];
    uint8_t transcript[32],cf[32],sf[32],sid[16],ab[16],ba[16];
    uint32_t limit,chosen;unsigned state;
} qboot_context;
void qboot_abort(qboot_context *ctx);
int qboot_init(qboot_context *ctx,const uint8_t psk[32],const uint8_t aid[16],const uint8_t bid[16],uint32_t limit);
int qboot_server_hello(qboot_context *ctx,const uint8_t *ch,size_t n,const uint8_t fresh_nonce[32],uint8_t reply[105]);
int qboot_server_finished(qboot_context *ctx,const uint8_t *cf,size_t n,uint8_t reply[69]);
int qboot_take_session(qboot_context *ctx,qas_context *session);
#endif
