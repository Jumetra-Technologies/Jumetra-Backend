#ifndef HHIP_SERIAL_TRANSPORT_H
#define HHIP_SERIAL_TRANSPORT_H

/*
 * UART/serial binding for hhip_transport_t (Sprint 36).
 *
 * Does not reimplement the HHIP envelope. send/receive call
 * hhip_send_message / hhip_receive_message from hhip_transport.c,
 * which already encode/decode via hhip_protocol.c and frame NDJSON
 * with a trailing '\n'.
 *
 * Board ports fill UART callbacks the same way hhip_hal.h fills
 * gpio/pwm/analog — no Arduino, ESP-IDF, or MCU register access here.
 */

#include "hhip_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef HHIP_SERIAL_DEFAULT_TIMEOUT_MS
#define HHIP_SERIAL_DEFAULT_TIMEOUT_MS 1000U
#endif

typedef struct hhip_uart_hal {
    void *ctx;
    /* Write `len` bytes. Return 0 on success, non-zero on failure. */
    int (*write)(void *ctx, const char *bytes, size_t len);
    /*
     * Read one byte if available.
     * Return 0 if *out was stored, 1 if no data, negative on error.
     */
    int (*read_byte)(void *ctx, unsigned char *out);
    /*
     * Optional monotonic millisecond clock used for receive timeout.
     * NULL: recv_line only consumes currently available bytes (no wait).
     */
    uint32_t (*millis)(void *ctx);
} hhip_uart_hal_t;

typedef struct hhip_serial_transport {
    hhip_uart_hal_t uart;
    uint32_t timeout_ms;
    char rx_buf[HHIP_LINE_MAX];
    size_t rx_len;
    uint32_t rx_started_ms;
    hhip_transport_t transport;
} hhip_serial_transport_t;

hhip_status_t hhip_serial_transport_init(hhip_serial_transport_t *serial,
                                         const hhip_uart_hal_t *uart,
                                         uint32_t timeout_ms);

/* Thin wrappers — call the Sprint 35 vtable helpers, not a second encoder. */
hhip_status_t hhip_serial_send_message(hhip_serial_transport_t *serial,
                                       const hhip_message_t *msg);
hhip_status_t hhip_serial_receive_message(hhip_serial_transport_t *serial,
                                          hhip_message_t *out);

#ifdef __cplusplus
}
#endif

#endif /* HHIP_SERIAL_TRANSPORT_H */
