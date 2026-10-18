/* The NV2A device model (nv2a.c) and its graphics engine (kelvin.c). */
#ifndef NV2A_H
#define NV2A_H

#include <stdint.h>

typedef struct {
    /* push buffer parser, kept across runs */
    uint32_t method, subch, count, ni;
    uint32_t object[8], class_[8]; /* what each subchannel is bound to */

    /* Kelvin (class 0x97) method state, indexed by method / 4 */
    uint32_t kelvin[0x2000 / 4];

    uint32_t vblanks, draws, clears;
} Nv2a;

extern Nv2a nv2a;

void rt_nv2a_init(void);
uint32_t nv2a_lookup(uint32_t handle);
uint32_t nv2a_dma_base(uint32_t inst, uint32_t *limit);
void nv2a_method(uint32_t subch, uint32_t method, uint32_t arg);
void nv2a_kelvin(uint32_t method, uint32_t arg);

#endif
