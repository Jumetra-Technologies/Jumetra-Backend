# HHIP Embedded SDK — host unit tests (Sprint 35)
#
# Portable C99. Protocol JSON uses vendored cJSON 1.7.18 (MIT), the
# same library already established for this wire format. No Arduino /
# ESP-IDF headers.
#
#   make test
#
# Always: -std=c99 -Wall -Wextra -Werror.
# AddressSanitizer / LeakSanitizer: enabled automatically when this CC
# can link them (typical on Linux). MSYS2 mingw64 compiler-rt does not
# ship libclang_rt.asan, and -fsanitize=leak is unsupported on
# x86_64-w64-windows-gnu; the test binary then still counts cJSON
# malloc/free and fails on outstanding allocations.
#
# Force sanitizers:  make test SANITIZE='-fsanitize=address,leak'

CC ?= gcc
CFLAGS ?= -std=c99 -Wall -Wextra -Werror -g -O1
LDFLAGS ?=

# Auto-detect ASan (and LSan when the driver accepts it).
SANITIZE ?= $(shell \
	echo 'int main(void){return 0;}' | $(CC) -fsanitize=address -x c - -o .hhip_asan_probe >/dev/null 2>&1 \
	&& ( echo 'int main(void){return 0;}' | $(CC) -fsanitize=address,leak -x c - -o .hhip_asan_probe >/dev/null 2>&1 \
		&& echo -fsanitize=address,leak || echo -fsanitize=address ) \
	|| true)

INCLUDES = \
	-Icore \
	-Ilifecycle \
	-Icapabilities \
	-Iprotocol \
	-Iprotocol/cjson \
	-Itransport \
	-Ihal

SRCS = \
	core/hhip_device.c \
	lifecycle/hhip_lifecycle.c \
	capabilities/hhip_capabilities.c \
	protocol/hhip_protocol.c \
	protocol/cjson/cJSON.c \
	transport/hhip_transport.c \
	transport/hhip_serial_transport.c \
	tests/test_sdk.c

BUILD_DIR = build
TARGET = $(BUILD_DIR)/test_sdk

.PHONY: all test clean

all: $(TARGET)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(TARGET): $(SRCS) | $(BUILD_DIR)
	$(CC) $(CFLAGS) $(SANITIZE) $(INCLUDES) -o $@ $(SRCS) $(LDFLAGS)
	@rm -f .hhip_asan_probe .hhip_asan_probe.exe

test: $(TARGET)
	$(TARGET)

clean:
	rm -rf $(BUILD_DIR) .hhip_asan_probe .hhip_asan_probe.exe
