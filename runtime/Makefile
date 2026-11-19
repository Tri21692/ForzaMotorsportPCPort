# Builds a native executable from xbrecomp's output and this runtime.
#
#   go run ./cmd/xbrecomp -o out/ default.xbe
#   make -C runtime GEN=../out -j$(nproc)
#   runtime/forza path/to/default.xbe
#
# The generated C needs gcc or clang on x86-64 (x87 long double) and must
# not use FMA contraction or fast math; see recomp/runtime/xbrt.h.

GEN ?= ../out
CC ?= gcc
OPT ?= -O1
GENFLAGS = $(OPT) -w -ffp-contract=off -fno-math-errno -fno-strict-aliasing -I$(GEN) $(OSFLAGS)
RTFLAGS = -O2 -g -Wall -Wextra -Wno-unused-parameter -ffp-contract=off -I$(GEN) $(OSFLAGS)

# Windows (MinGW-w64, e.g. w64devkit): the generated files have more
# sections than a COFF object normally allows, and file offsets are 64-bit.
ifeq ($(OS),Windows_NT)
EXE = .exe
OSFLAGS = -Wa,-mbig-obj -D_FILE_OFFSET_BITS=64
OSLIBS = -lwinmm -lgdi32 -lopengl32 -ld3d11 -ldxgi -ldxguid -lwinhttp -lws2_32 -lbcrypt -lshell32 -lole32
endif

GEN_SRC = $(wildcard $(GEN)/*.c)
GEN_OBJ = $(patsubst $(GEN)/%.c,build/gen/%.o,$(GEN_SRC))
RT_SRC = main.c mem.c thread.c kernel.c file.c dpc.c hw.c nv2a.c kelvin.c apu.c apu_vp.c hle_input.c hle_net.c hle_fiber.c hle_d3d.c hle_career.c hle_drift.c hle_rival.c hle_kaizo.c hle_elim.c hle_mayhemcar.c hle_career_panel.c hle_career_cats.c hle_cheats.c hle_qol.c hle_clip.c hle_achieve.c hle_minigame.c hle_quickrace.c hle_listcheck.c hle_fclass.c hle_unlock.c crypto.c inflate.c display.c raster.c gl.c hdr.c settings.c overlay.c soundtrack.c spotify.c
RT_OBJ = $(patsubst %.c,build/%.o,$(RT_SRC))

TARGET ?= forza$(EXE)

$(TARGET): $(GEN_OBJ) $(RT_OBJ) build/wraps.o
	$(CC) -o $@ $^ -lm -lpthread $(OSLIBS)

# The game functions the runtime replaces and still calls (wraps.txt), copied from the generated
# code at build time as orig_f_<address> (wraps.awk): never committed, as the generated code is not.
build/wraps.c: wraps.txt wraps.awk $(GEN_SRC)
	@mkdir -p build
	awk -f wraps.awk wraps.txt $(GEN_SRC) > $@

build/wraps.o: build/wraps.c $(GEN)/xbrt.h $(GEN)/funcs.h
	$(CC) $(GENFLAGS) -c $< -o $@

build/gen/%.o: $(GEN)/%.c $(GEN)/xbrt.h $(GEN)/funcs.h
	@mkdir -p build/gen
	$(CC) $(GENFLAGS) -c $< -o $@

build/%.o: %.c rt.h nv2a.h $(GEN)/xbrt.h $(GEN)/names.h
	@mkdir -p build
	$(CC) $(RTFLAGS) -c $< -o $@

# Files #included by others, and the GL header.
build/raster.o: glfill.c glvsh.c glover.c glfs.c gl.h glcache.h gltexhd.c
build/gl.o build/nv2a.o: gl.h

clean:
	rm -rf build forza forza.exe

.PHONY: clean

# (the copied game functions it includes)
build/hle_career_cats.o: hle_career_cats_gen.inc
