/* ============================================================================
 * Authenticated Classical Channel: Wegman-Carter MAC Wrapper
 * Implementation for Xilinx ZC702 Post-Processing Subsystem
 * ============================================================================ */

#include "auth_channel.h"
#include <string.h>

/* GF(2^64) multiplication modulo P(x) = x^64 + x^4 + x^3 + x + 1 (0x1B) */
static uint64_t gf64_mul(uint64_t a, uint64_t b)
{
    uint64_t res = 0;
    while (b > 0) {
        if (b & 1u) {
            res ^= a;
        }
        uint64_t carry = a >> 63;
        a <<= 1;
        if (carry) {
            a ^= 0x000000000000001Bu; /* Irreducible polynomial reduction */
        }
        b >>= 1;
    }
    return res;
}

/* Computational masking prototype. The legacy API supplies only 64 PSK bits;
 * deriving two words below does not create a 128-bit independent secret key.
 * siphash24_64 implements standard SipHash-2-4 for exactly eight input bytes. */
static inline uint64_t rotl64(uint64_t x, int b)
{
    return (x << b) | (x >> (64 - b));
}

#define SIPROUND do { \
    v0 += v1; v1 = rotl64(v1, 13); v1 ^= v0; v0 = rotl64(v0, 32); \
    v2 += v3; v3 = rotl64(v3, 16); v3 ^= v2; \
    v0 += v3; v3 = rotl64(v3, 21); v3 ^= v0; \
    v2 += v1; v1 = rotl64(v1, 17); v1 ^= v2; v2 = rotl64(v2, 32); \
} while (0)

static uint64_t siphash24_64(uint64_t k0, uint64_t k1, uint64_t m)
{
    uint64_t v0 = 0x736f6d6570736575ULL ^ k0;
    uint64_t v1 = 0x646f72616e646f6dULL ^ k1;
    uint64_t v2 = 0x6c7967656e657261ULL ^ k0;
    uint64_t v3 = 0x7465646279746573ULL ^ k1;

    v3 ^= m;
    SIPROUND;
    SIPROUND;
    v0 ^= m;

    /* Even an exact full block requires the final length/tail block. */
    const uint64_t tail = UINT64_C(8) << 56;
    v3 ^= tail;
    SIPROUND;
    SIPROUND;
    v0 ^= tail;

    v2 ^= 0xff;
    SIPROUND;
    SIPROUND;
    SIPROUND;
    SIPROUND;

    return v0 ^ v1 ^ v2 ^ v3;
}

static uint64_t derive_otp(uint64_t psk, uint32_t seq, uint16_t msg_type)
{
    uint64_t k0 = psk;
    uint64_t k1 = psk ^ 0x9E3779B97F4A7C15ULL;
    uint64_t m = ((uint64_t)msg_type << 32) | (uint64_t)seq;
    return siphash24_64(k0, k1, m);
}

void auth_channel_init(auth_context_t *ctx, uint64_t hash_key, uint64_t psk_seed)
{
    if (!ctx) return;
    memset(ctx, 0, sizeof(*ctx));
    ctx->hash_key = hash_key;
    ctx->psk_seed = psk_seed;
    ctx->last_rx_seq = 0u;
    ctx->tx_seq = 1u;
    ctx->packets_authenticated = 0u;
    ctx->forgeries_detected = 0u;
    ctx->replays_rejected = 0u;
    /* Invalid provisioning must never silently install public fallback keys. */
    ctx->locked_out = (hash_key == 0u || psk_seed == 0u);
    ctx->has_rx_any = false;
}

uint64_t auth_channel_compute_mac(const auth_context_t *ctx,
                                  const uint8_t *payload,
                                  uint32_t len,
                                  uint32_t seq,
                                  uint16_t msg_type)
{
    if (!ctx) return 0;

    /* Polynomial evaluation over GF(2^64) */
    uint64_t acc = 0;
    uint32_t words64 = len / 8u;
    const uint64_t *words = (const uint64_t *)payload;

    for (uint32_t i = 0; i < words64; i++) {
        uint64_t block = words[i];
        acc = gf64_mul(acc ^ block, ctx->hash_key);
    }

    /* Handle partial remaining bytes */
    uint32_t rem = len % 8u;
    if (rem > 0) {
        uint64_t block = 0;
        memcpy(&block, payload + words64 * 8u, rem);
        acc = gf64_mul(acc ^ block, ctx->hash_key);
    }

    /* Append message length block with non-zero domain separator */
    uint64_t len_block = 0x8000000000000000ULL | ((uint64_t)msg_type << 32) | (uint64_t)len;
    acc = gf64_mul(acc ^ len_block, ctx->hash_key);

    /* Apply OTP mask derived via SipHash-2-4 PRF */
    uint64_t otp = derive_otp(ctx->psk_seed, seq, msg_type);
    return acc ^ otp;
}

int auth_channel_wrap(auth_context_t *ctx,
                      uint16_t msg_type,
                      const uint8_t *payload,
                      uint32_t len,
                      uint8_t *out_buf,
                      uint32_t *out_len)
{
    if (!ctx || !out_buf || !out_len || len > AUTH_MAX_PAYLOAD || (len && !payload)) {
        return -1;
    }
    if (ctx->locked_out) {
        return AUTH_ERR_LOCKOUT;
    }

    /* Rekey before exhaustion; never reuse sequence zero after wraparound. */
    if (ctx->tx_seq == UINT32_MAX) {
        ctx->locked_out = true;
        return AUTH_ERR_LOCKOUT;
    }

    uint32_t seq = ctx->tx_seq++;
    uint64_t mac = auth_channel_compute_mac(ctx, payload, len, seq, msg_type);

    auth_header_t hdr;
    hdr.magic = AUTH_MAGIC;
    hdr.seq = seq;
    hdr.msg_type = msg_type;
    hdr.payload_len = (uint16_t)len;
    hdr.tag_low = (uint32_t)mac;
    hdr.tag_high = (uint32_t)(mac >> 32);

    memcpy(out_buf, &hdr, sizeof(hdr));
    if (payload && len > 0) {
        memcpy(out_buf + sizeof(hdr), payload, len);
    }
    *out_len = sizeof(hdr) + len;
    return 0;
}

auth_status_t auth_channel_unwrap_and_verify(auth_context_t *ctx,
                                             const uint8_t *in_packet,
                                             uint32_t in_len,
                                             uint16_t *out_msg_type,
                                             const uint8_t **out_payload,
                                             uint32_t *out_payload_len)
{
    if (!ctx || !in_packet || in_len < sizeof(auth_header_t)) {
        return AUTH_ERR_PAYLOAD_LEN;
    }
    if (ctx->locked_out) {
        return AUTH_ERR_LOCKOUT;
    }

    const auth_header_t *hdr = (const auth_header_t *)in_packet;

    /* Verify Magic Word */
    if (hdr->magic != AUTH_MAGIC) {
        return AUTH_ERR_MAGIC;
    }

    /* Check packet length */
    if (in_len != sizeof(auth_header_t) + (uint32_t)hdr->payload_len) {
        return AUTH_ERR_PAYLOAD_LEN;
    }

    /* Enforce strict sequence monotonicity (anti-replay guard) */
    if (ctx->has_rx_any && hdr->seq <= ctx->last_rx_seq) {
        ctx->replays_rejected++;
        return AUTH_ERR_REPLAY_SEQ;
    }

    /* Compute expected Wegman-Carter MAC */
    const uint8_t *payload = in_packet + sizeof(auth_header_t);
    uint64_t expected_mac = auth_channel_compute_mac(ctx, payload, hdr->payload_len,
                                                    hdr->seq, hdr->msg_type);
    uint64_t received_mac = (uint64_t)hdr->tag_low | ((uint64_t)hdr->tag_high << 32);

    /* Constant-time MAC comparison */
    uint64_t diff = expected_mac ^ received_mac;
    if (diff != 0u) {
        ctx->forgeries_detected++;
        return AUTH_ERR_TAG_MISMATCH;
    }

    /* Authentication succeeded: advance sequence counter */
    ctx->has_rx_any = true;
    ctx->last_rx_seq = hdr->seq;
    ctx->packets_authenticated++;

    if (out_msg_type) *out_msg_type = hdr->msg_type;
    if (out_payload) *out_payload = payload;
    if (out_payload_len) *out_payload_len = (uint32_t)hdr->payload_len;

    return AUTH_OK;
}

double auth_channel_calc_epsilon_auth(const auth_context_t *ctx)
{
    (void)ctx;
    /* No composable authentication bound is established for this prototype.
     * Returning 1 prevents callers from interpreting N/2^64 as certification. */
    return 1.0;
}
