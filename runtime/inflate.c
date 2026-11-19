/* Inflating a zlib stream (RFC 1950 and 1951), after Mark Adler's puff:
 * enough for the runtime to see what the disc's installer archives unpack
 * to (file.c). Slow and small; nothing in the game's own paths uses it. */
#include <setjmp.h>
#include <string.h>

#include "rt.h"

typedef struct {
    const uint8_t *in;
    size_t inlen, incnt;
    uint32_t bitbuf, bitcnt;
    uint8_t *out;
    size_t outlen, outcnt;
    jmp_buf env; /* out of input */
} State;

typedef struct {
    short *count, *symbol;
} Huff;

static uint32_t bits(State *s, uint32_t need) {
    uint32_t val = s->bitbuf;
    while (s->bitcnt < need) {
        if (s->incnt == s->inlen) longjmp(s->env, 1);
        val |= (uint32_t)s->in[s->incnt++] << s->bitcnt;
        s->bitcnt += 8;
    }
    s->bitbuf = val >> need;
    s->bitcnt -= need;
    return val & ((1u << need) - 1);
}

static int stored(State *s) {
    s->bitbuf = s->bitcnt = 0; /* to the byte boundary */
    if (s->incnt + 4 > s->inlen) return -1;
    const uint8_t *p = s->in + s->incnt;
    uint32_t len = p[0] | p[1] << 8, nlen = p[2] | p[3] << 8;
    s->incnt += 4;
    if (len != (~nlen & 0xFFFF) || s->incnt + len > s->inlen || s->outcnt + len > s->outlen) return -1;
    memcpy(s->out + s->outcnt, s->in + s->incnt, len);
    s->outcnt += len, s->incnt += len;
    return 0;
}

static int decode(State *s, const Huff *h) {
    int code = 0, first = 0, index = 0;
    for (int len = 1; len <= 15; len++) {
        code |= bits(s, 1);
        int count = h->count[len];
        if (code - count < first) return h->symbol[index + (code - first)];
        index += count, first += count;
        first <<= 1, code <<= 1;
    }
    return -1;
}

/* Canonical codes from code lengths: 0 complete, > 0 incomplete, < 0 over-subscribed. */
static int construct(Huff *h, const short *length, int n) {
    short offs[16];
    memset(h->count, 0, 16 * sizeof(short));
    for (int i = 0; i < n; i++) h->count[length[i]]++;
    if (h->count[0] == n) return 0;
    int left = 1;
    for (int len = 1; len <= 15; len++) {
        left <<= 1, left -= h->count[len];
        if (left < 0) return left;
    }
    offs[1] = 0;
    for (int len = 1; len < 15; len++) offs[len + 1] = offs[len] + h->count[len];
    for (int i = 0; i < n; i++)
        if (length[i]) h->symbol[offs[length[i]]++] = (short)i;
    return left;
}

static int codes(State *s, const Huff *lencode, const Huff *distcode) {
    static const short lbase[29] = {3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31,
                                    35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
    static const short lext[29] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
    static const short dbase[30] = {1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385,
                                    513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577};
    static const short dext[30] = {0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};
    for (;;) {
        int symbol = decode(s, lencode);
        if (symbol < 0) return -1;
        if (symbol == 256) return 0;
        if (symbol < 256) {
            if (s->outcnt == s->outlen) return -1;
            s->out[s->outcnt++] = (uint8_t)symbol;
            continue;
        }
        symbol -= 257;
        if (symbol >= 29) return -1;
        size_t len = lbase[symbol] + bits(s, lext[symbol]);
        symbol = decode(s, distcode);
        if (symbol < 0 || symbol >= 30) return -1;
        size_t dist = dbase[symbol] + bits(s, dext[symbol]);
        if (dist > s->outcnt || s->outcnt + len > s->outlen) return -1;
        for (; len; len--, s->outcnt++) s->out[s->outcnt] = s->out[s->outcnt - dist];
    }
}

static int fixed(State *s) {
    static short lencnt[16], lensym[288], distcnt[16], distsym[30];
    static Huff lencode = {lencnt, lensym}, distcode = {distcnt, distsym};
    static int built;
    if (!built) {
        short lengths[288];
        int i = 0;
        for (; i < 144; i++) lengths[i] = 8;
        for (; i < 256; i++) lengths[i] = 9;
        for (; i < 280; i++) lengths[i] = 7;
        for (; i < 288; i++) lengths[i] = 8;
        construct(&lencode, lengths, 288);
        for (i = 0; i < 30; i++) lengths[i] = 5;
        construct(&distcode, lengths, 30);
        built = 1;
    }
    return codes(s, &lencode, &distcode);
}

static int dynamic(State *s) {
    static const short order[19] = {16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15};
    short lengths[320], lencnt[16], lensym[286], distcnt[16], distsym[30];
    Huff lencode = {lencnt, lensym}, distcode = {distcnt, distsym};
    int nlen = bits(s, 5) + 257, ndist = bits(s, 5) + 1, ncode = bits(s, 4) + 4;
    if (nlen > 286 || ndist > 30) return -1;
    int index = 0;
    for (; index < ncode; index++) lengths[order[index]] = (short)bits(s, 3);
    for (; index < 19; index++) lengths[order[index]] = 0;
    if (construct(&lencode, lengths, 19) != 0) return -1;
    for (index = 0; index < nlen + ndist;) {
        int symbol = decode(s, &lencode), len = 0;
        if (symbol < 0) return -1;
        if (symbol < 16) {
            lengths[index++] = (short)symbol;
            continue;
        }
        if (symbol == 16) {
            if (!index) return -1;
            len = lengths[index - 1], symbol = 3 + bits(s, 2);
        } else if (symbol == 17) {
            symbol = 3 + bits(s, 3);
        } else {
            symbol = 11 + bits(s, 7);
        }
        if (index + symbol > nlen + ndist) return -1;
        while (symbol--) lengths[index++] = (short)len;
    }
    if (!lengths[256]) return -1;
    int err = construct(&lencode, lengths, nlen);
    if (err < 0 || (err > 0 && nlen - lencode.count[0] != 1)) return -1;
    err = construct(&distcode, lengths + nlen, ndist);
    if (err < 0 || (err > 0 && ndist - distcode.count[0] != 1)) return -1;
    return codes(s, &lencode, &distcode);
}

long rt_inflate(const uint8_t *in, size_t n, uint8_t *out, size_t cap, size_t *used) {
    if (n < 6 || (in[0] & 15) != 8 || ((in[0] << 8) | in[1]) % 31 || (in[1] & 0x20)) return -1;
    State s;
    s.in = in + 2, s.inlen = n - 2, s.incnt = 0, s.bitbuf = s.bitcnt = 0;
    s.out = out, s.outlen = cap, s.outcnt = 0;
    if (setjmp(s.env)) return -1;
    for (int last = 0; !last;) {
        last = bits(&s, 1);
        uint32_t type = bits(&s, 2);
        int err = type == 0 ? stored(&s) : type == 1 ? fixed(&s) : type == 2 ? dynamic(&s) : -1;
        if (err) return -1;
    }
    if (s.incnt + 4 > s.inlen) return -1;
    uint32_t a = 1, b = 0; /* Adler-32 */
    for (size_t i = 0; i < s.outcnt; i++) a = (a + out[i]) % 65521, b = (b + a) % 65521;
    const uint8_t *p = s.in + s.incnt;
    if ((b << 16 | a) != ((uint32_t)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3])) return -1;
    *used = 2 + s.incnt + 4;
    return (long)s.outcnt;
}
