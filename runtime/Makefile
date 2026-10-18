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
OSLIBS = -lwinmm -lgdi32
endif

GEN_SRC = $(wildcard $(GEN)/*.c)
GEN_OBJ = $(patsubst $(GEN)/%.c,build/gen/%.o,$(GEN_SRC))
RT_SRC = main.c mem.c thread.c kernel.c file.c dpc.c hw.c nv2a.c kelvin.c apu.c hle_input.c hle_net.c hle_fiber.c crypto.c display.c
RT_OBJ = $(patsubst %.c,build/%.o,$(RT_SRC))

forza$(EXE): $(GEN_OBJ) $(RT_OBJ)
	$(CC) -o $@ $^ -lm -lpthread $(OSLIBS)

build/gen/%.o: $(GEN)/%.c $(GEN)/xbrt.h $(GEN)/funcs.h
	@mkdir -p build/gen
	$(CC) $(GENFLAGS) -c $< -o $@

build/%.o: %.c rt.h nv2a.h $(GEN)/xbrt.h $(GEN)/names.h
	@mkdir -p build
	$(CC) $(RTFLAGS) -c $< -o $@

clean:
	rm -rf build forza forza.exe

.PHONY: clean
