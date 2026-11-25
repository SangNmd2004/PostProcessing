#ifndef QKD_QCRYPTO_H
#define QKD_QCRYPTO_H
#include <stddef.h>
#include <stdint.h>
void qcrypto_wipe(void *p,size_t n);
int qcrypto_sha256(const uint8_t *data,size_t n,uint8_t out[32]);
int qcrypto_hmac(const uint8_t *key,size_t key_n,const uint8_t *data,size_t n,uint8_t out[32]);
/* Bounded wrapper for bootstrap info, not a general unbounded allocation API. */
int qcrypto_hkdf(const uint8_t *ikm,size_t ikm_n,const uint8_t *salt,size_t salt_n,
                 const uint8_t *info,size_t info_n,uint8_t *out,size_t out_n);
#endif
