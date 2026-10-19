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

    uint32_t vblanks, draws, clears, flips, traps, skipped;
} Nv2a;

extern Nv2a nv2a;

void rt_nv2a_init(void);
uint32_t nv2a_lookup(uint32_t handle);
uint32_t nv2a_dma_base(uint32_t inst, uint32_t *limit);
void nv2a_method(uint32_t subch, uint32_t method, uint32_t arg);
void nv2a_kelvin(uint32_t method, uint32_t arg);
void nv2a_raster_method(uint32_t method, uint32_t arg); /* raster.c: draws in software */
void nv2a_raster_invalidate(void);                      /* textures may have changed */
void nv2a_raster_flush(void);                           /* finish the batched drawing */
void nv2a_raster_sync(void);
void nv2a_raster_sync_range(uint32_t base, uint32_t size); /* the colour drawn over these bytes on its way to RAM */
void nv2a_raster_flip(void);                            /* at FLIP_INCREMENT_WRITE */
void nv2a_raster_vblank(void);                          /* read-backs on their way reach RAM */
int nv2a_raster_clear(uint32_t flags);                  /* CLEAR_SURFACE on the GPU; 0 if it is not drawing */                            /* and bring RAM up to date with the GPU's drawing */

#endif
