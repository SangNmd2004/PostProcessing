/* ============================================================================
 * Authenticated Classical Channel: Wegman-Carter MAC Wrapper
 * Target: Xilinx ZC702 (ARM Cortex-A9)
 * Reference: Work item P04, Wegman & Carter (1981), Stinson (1994)
 *
 * Provides information-theoretically secure classical message authentication:
 *  1. Universal hash polynomial evaluation over GF(2^64).
 *  2. One-time pad OTP masking derived from pre-shared key (PSK) and seq.
 *  3. Strict anti-replay sequence monotonicity checking.
 *  4. Fail-closed packet drop on tag mismatch or replay attempt.
 * ============================================================================ */

#ifndef AUTH_CHANNEL_H
#define AUTH_CHANNEL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define AUTH_MAGIC          0x51415554u /* 'QAUT' */
#define AUTH_TAG_BYTES      8u          /* 64-bit authentication tag */
#define AUTH_MAX_PAYLOAD    16384u      /* Max classical message payload bytes */

typedef enum {
    AUTH_OK              = 0,
    AUTH_ERR_MAGIC       = -1,
    AUTH_ERR_REPLAY_SEQ  = -2,
    AUTH_ERR_TAG_MISMATCH= -3,
    AUTH_ERR_PAYLOAD_LEN = -4,
    AUTH_ERR_LOCKOUT     = -5
} auth_status_t;

/* Authenticated packet header (16 bytes) */
typedef struct __attribute__((packed)) {
    uint32_t magic;         /* AUTH_MAGIC */
    uint32_t seq;           /* Monotonically increasing sequence number */
    uint16_t msg_type;      /* Message opcode (SYNDROME, REVEAL, TAG, etc.) */
    uint16_t payload_len;   /* Payload byte length */
    uint32_t tag_low;       /* 64-bit Wegman-Carter MAC tag */
    uint32_t tag_high;
} auth_header_t;

/* Channel authentication context */
typedef struct {
    uint64_t hash_key;              /* Universal hash evaluation key in GF(2^64) */
    uint64_t psk_seed;              /* Pre-shared secret key for OTP generation */
    uint32_t last_rx_seq;           /* Anti-replay sequence counter */
    uint32_t tx_seq;                /* Outgoing sequence counter */
    uint32_t packets_authenticated; /* Successful packets verified */
    uint32_t forgeries_detected;    /* Corrupted or tampered packets dropped */
    uint32_t replays_rejected;      /* Replay packets blocked */
    bool     locked_out;            /* Fail-closed security lockout flag */
    bool     has_rx_any;            /* True if at least one packet has been accepted */
} auth_context_t;

/* Initialize authenticated channel with Pre-Shared Key (PSK) */
void auth_channel_init(auth_context_t *ctx, uint64_t hash_key, uint64_t psk_seed);

/* Compute 64-bit Wegman-Carter MAC over payload with given sequence number */
uint64_t auth_channel_compute_mac(const auth_context_t *ctx,
                                  const uint8_t *payload,
                                  uint32_t len,
                                  uint32_t seq,
                                  uint16_t msg_type);

/* Wrap an outgoing message with an authenticated header */
int auth_channel_wrap(auth_context_t *ctx,
                      uint16_t msg_type,
                      const uint8_t *payload,
                      uint32_t len,
                      uint8_t *out_buf,
                      uint32_t *out_len);

/* Verify and unwrap an incoming authenticated packet.
 * Enforces strict sequence monotonicity and 64-bit MAC verification. */
auth_status_t auth_channel_unwrap_and_verify(auth_context_t *ctx,
                                             const uint8_t *in_packet,
                                             uint32_t in_len,
                                             uint16_t *out_msg_type,
                                             const uint8_t **out_payload,
                                             uint32_t *out_payload_len);

/* Query channel security status */
double auth_channel_calc_epsilon_auth(const auth_context_t *ctx);

#ifdef __cplusplus
}
#endif

#endif /* AUTH_CHANNEL_H */
