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
GENFLAGS = $(OPT) -w -ffp-contract=off -fno-math-errno -fno-strict-aliasing -I$(GEN)
RTFLAGS = -O2 -g -Wall -Wextra -Wno-unused-parameter -ffp-contract=off -I$(GEN)

GEN_SRC = $(wildcard $(GEN)/*.c)
GEN_OBJ = $(patsubst $(GEN)/%.c,build/gen/%.o,$(GEN_SRC))
RT_SRC = main.c mem.c thread.c kernel.c file.c dpc.c hle_input.c
RT_OBJ = $(patsubst %.c,build/%.o,$(RT_SRC))

forza: $(GEN_OBJ) $(RT_OBJ)
	$(CC) -o $@ $^ -lm -lpthread

build/gen/%.o: $(GEN)/%.c $(GEN)/xbrt.h $(GEN)/funcs.h
	@mkdir -p build/gen
	$(CC) $(GENFLAGS) -c $< -o $@

build/%.o: %.c rt.h $(GEN)/xbrt.h $(GEN)/names.h
	@mkdir -p build
	$(CC) $(RTFLAGS) -c $< -o $@

clean:
	rm -rf build forza

.PHONY: clean
