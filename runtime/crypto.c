/* The kernel's crypto exports (Xc*), which games use to sign saves:
 * SHA-1, HMAC-SHA1 and RC4.
 *
 * The SHA context lives in the caller's buffer (XAPI gives the kernel an
 * A_SHA_CTX of 116 bytes); only these functions read it, so the layout is
 * this file's own: state (+0), byte count (+20), buffered bytes (+28),
 * buffer (+32). The RC4 key structure is S[256], then i and j.
 *
 * The key exports (XboxSignatureKey and the rest) are zeroed in this
 * runtime, so signatures are consistent on this machine but saves do not
 * move to or from a real console.
 */
#include <string.h>

#include "rt.h"

#define ARG(i) xb_rd32(c->esp + 4 + 4 * (i))

/* ---- SHA-1 ---- */

typedef struct {
    uint32_t h[5];
    uint64_t n;
    uint32_t len;
    uint8_t buf[64];
} Sha1;

static uint32_t rol(uint32_t x, int k) { return x << k | x >> (32 - k); }

static void sha1_block(Sha1 *s, const uint8_t *p) {
    uint32_t w[80], a = s->h[0], b = s->h[1], c = s->h[2], d = s->h[3], e = s->h[4];
    for (int i = 0; i < 16; i++) w[i] = (uint32_t)p[4 * i] << 24 | p[4 * i + 1] << 16 | p[4 * i + 2] << 8 | p[4 * i + 3];
    for (int i = 16; i < 80; i++) w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    for (int i = 0; i < 80; i++) {
        uint32_t f, k;
        if (i < 20) f = (b & c) | (~b & d), k = 0x5A827999u;
        else if (i < 40) f = b ^ c ^ d, k = 0x6ED9EBA1u;
        else if (i < 60) f = (b & c) | (b & d) | (c & d), k = 0x8F1BBCDCu;
        else f = b ^ c ^ d, k = 0xCA62C1D6u;
        uint32_t t = rol(a, 5) + f + e + k + w[i];
        e = d, d = c, c = rol(b, 30), b = a, a = t;
    }
    s->h[0] += a, s->h[1] += b, s->h[2] += c, s->h[3] += d, s->h[4] += e;
}

static void sha1_init(Sha1 *s) {
    static const uint32_t iv[5] = {0x67452301u, 0xEFCDAB89u, 0x98BADCFEu, 0x10325476u, 0xC3D2E1F0u};
    memcpy(s->h, iv, sizeof iv);
    s->n = 0, s->len = 0;
}

static void sha1_update(Sha1 *s, const uint8_t *p, uint32_t n) {
    s->n += n;
    while (n) {
        uint32_t k = 64 - s->len < n ? 64 - s->len : n;
        memcpy(s->buf + s->len, p, k);
        s->len += k, p += k, n -= k;
        if (s->len == 64) {
            sha1_block(s, s->buf);
            s->len = 0;
        }
    }
}

static void sha1_final(Sha1 *s, uint8_t out[20]) {
    uint64_t bits = s->n * 8;
    uint8_t pad = 0x80, zero = 0, len[8];
    sha1_update(s, &pad, 1);
    while (s->len != 56) sha1_update(s, &zero, 1);
    for (int i = 0; i < 8; i++) len[i] = (uint8_t)(bits >> (56 - 8 * i));
    sha1_update(s, len, 8);
    for (int i = 0; i < 5; i++)
        out[4 * i] = (uint8_t)(s->h[i] >> 24), out[4 * i + 1] = (uint8_t)(s->h[i] >> 16),
        out[4 * i + 2] = (uint8_t)(s->h[i] >> 8), out[4 * i + 3] = (uint8_t)s->h[i];
}

/* The context is kept in guest memory between calls. */
static void ctx_load(uint32_t a, Sha1 *s) {
    memcpy(s->h, xb_mem + a, 20);
    memcpy(&s->n, xb_mem + a + 20, 8);
    memcpy(&s->len, xb_mem + a + 28, 4);
    memcpy(s->buf, xb_mem + a + 32, 64);
}
static void ctx_store(uint32_t a, const Sha1 *s) {
    memcpy(xb_mem + a, s->h, 20);
    memcpy(xb_mem + a + 20, &s->n, 8);
    memcpy(xb_mem + a + 28, &s->len, 4);
    memcpy(xb_mem + a + 32, s->buf, 64);
}

/* VOID XcSHAInit(PUCHAR pbSHAContext) */
static uint32_t k_XcSHAInit(XbCtx *c) {
    Sha1 s;
    sha1_init(&s);
    ctx_store(ARG(0), &s);
    return 0;
}

/* VOID XcSHAUpdate(PUCHAR pbSHAContext, PUCHAR pbInput, ULONG dwInputLength) */
static uint32_t k_XcSHAUpdate(XbCtx *c) {
    Sha1 s;
    ctx_load(ARG(0), &s);
    sha1_update(&s, xb_mem + ARG(1), ARG(2));
    ctx_store(ARG(0), &s);
    return 0;
}

/* VOID XcSHAFinal(PUCHAR pbSHAContext, PUCHAR pbDigest) */
static uint32_t k_XcSHAFinal(XbCtx *c) {
    Sha1 s;
    ctx_load(ARG(0), &s);
    sha1_final(&s, xb_mem + ARG(1));
    return 0;
}

/* VOID XcHMAC(PBYTE pbKey, DWORD dwKeyLength, PBYTE pbInput, DWORD dwInputLength,
 *             PBYTE pbInput2, DWORD dwInputLength2, PBYTE pbDigest):
 * HMAC-SHA1 of the two inputs, one after the other. */
static uint32_t k_XcHMAC(XbCtx *c) {
    uint8_t key[64] = {0}, pad[64], inner[20];
    uint32_t klen = ARG(1);
    if (klen > 64) {
        Sha1 s;
        sha1_init(&s);
        sha1_update(&s, xb_mem + ARG(0), klen);
        sha1_final(&s, key);
    } else {
        memcpy(key, xb_mem + ARG(0), klen);
    }
    Sha1 s;
    for (int i = 0; i < 64; i++) pad[i] = key[i] ^ 0x36;
    sha1_init(&s);
    sha1_update(&s, pad, 64);
    if (ARG(2)) sha1_update(&s, xb_mem + ARG(2), ARG(3));
    if (ARG(4)) sha1_update(&s, xb_mem + ARG(4), ARG(5));
    sha1_final(&s, inner);
    for (int i = 0; i < 64; i++) pad[i] = key[i] ^ 0x5C;
    sha1_init(&s);
    sha1_update(&s, pad, 64);
    sha1_update(&s, inner, 20);
    sha1_final(&s, xb_mem + ARG(6));
    return 0;
}

/* ---- RC4 ---- */

/* VOID XcRC4Key(PUCHAR pbKeyStruct, ULONG dwKeyLength, PUCHAR pbKey) */
static uint32_t k_XcRC4Key(XbCtx *c) {
    uint8_t *st = xb_mem + ARG(0), *key = xb_mem + ARG(2);
    uint32_t n = ARG(1);
    for (int i = 0; i < 256; i++) st[i] = (uint8_t)i;
    for (int i = 0, j = 0; i < 256 && n; i++) {
        j = (j + st[i] + key[i % n]) & 0xFF;
        uint8_t t = st[i];
        st[i] = st[j], st[j] = t;
    }
    st[256] = st[257] = 0;
    return 0;
}

/* VOID XcRC4Crypt(PUCHAR pbKeyStruct, ULONG dwInputLength, PUCHAR pbInput): in place */
static uint32_t k_XcRC4Crypt(XbCtx *c) {
    uint8_t *st = xb_mem + ARG(0), *p = xb_mem + ARG(2);
    uint8_t i = st[256], j = st[257];
    for (uint32_t k = 0; k < ARG(1); k++) {
        i = (uint8_t)(i + 1);
        j = (uint8_t)(j + st[i]);
        uint8_t t = st[i];
        st[i] = st[j], st[j] = t;
        p[k] ^= st[(uint8_t)(st[i] + st[j])];
    }
    st[256] = i, st[257] = j;
    return 0;
}

void rt_crypto_init(void) {
    rt_kernel_handler(335, k_XcSHAInit);
    rt_kernel_handler(336, k_XcSHAUpdate);
    rt_kernel_handler(337, k_XcSHAFinal);
    rt_kernel_handler(338, k_XcRC4Key);
    rt_kernel_handler(339, k_XcRC4Crypt);
    rt_kernel_handler(340, k_XcHMAC);
}
