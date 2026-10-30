#ifndef QKD_AUTH_SESSION_H
#define QKD_AUTH_SESSION_H
#include <stdint.h>
#include <stdbool.h>

/* Computational MAC prototype, separate from baseline UART and the legacy
 * auth_channel API. A trusted handshake/key provisioner must supply a fresh
 * session ID and independent per-direction 128-bit keys. No handshake, durable
 * anti-rollback, information-theoretic bound or entropy source is implemented. */
#define QAS_HEADER_BYTES 32u
#define QAS_TAG_BYTES 8u
#define QAS_MAX_PAYLOAD 16384u
#define QAS_MAX_PACKETS 1000000u /* Operational limit, not an epsilon proof. */

typedef enum {QAS_ALICE=0,QAS_BOB=1} qas_role;
typedef enum {
    QAS_OK=0,QAS_CLOSED=-1,QAS_ARGUMENT=-2,QAS_FORMAT=-3,
    QAS_SESSION=-4,QAS_DIRECTION=-5,QAS_REPLAY=-6,QAS_BAD_TAG=-7,
    QAS_EXHAUSTED=-8,QAS_CAPACITY=-9
} qas_status;
typedef struct {
    uint8_t sid[16],tx_key[16],rx_key[16];
    uint32_t tx_next,rx_last,tx_used,rx_checks,limit;
    uint8_t tx_direction;
    bool active;
} qas_context;

/* Must initialize before open. Reset clears keys and leaves transport closed. */
void qas_reset(qas_context *ctx);
/* Explicit trusted provisioning only. Never call in response to an untrusted
 * packet. Reopening the same SID/key after reset remains a caller-side security
 * violation which this volatile module cannot detect. */
qas_status qas_open(qas_context *ctx,qas_role role,const uint8_t sid[16],
                    const uint8_t alice_to_bob[16],const uint8_t bob_to_alice[16],
                    uint32_t packet_limit);
qas_status qas_wrap(qas_context *ctx,uint16_t opcode,const uint8_t *payload,
                    uint32_t length,uint8_t *frame,uint32_t capacity,uint32_t *written);
/* On success payload borrows the caller-owned authenticated frame. Keep that
 * buffer immutable until command dispatch completes. Outputs clear on failure.
 * Failed MAC checks consume budget; malformed/replayed frames do not run MAC. */
qas_status qas_unwrap(qas_context *ctx,const uint8_t *frame,uint32_t length,
                      uint16_t *opcode,const uint8_t **payload,uint32_t *payload_length);
#endif
