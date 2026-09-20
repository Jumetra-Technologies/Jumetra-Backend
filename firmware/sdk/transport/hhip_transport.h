#ifndef HHIP_TRANSPORT_H
#define HHIP_TRANSPORT_H

/*
 * Transport-agnostic send/receive (Sprint 35).
 *
 * This is the envelope-aware glue over a byte/line vtable. It does not
 * implement UART, WiFi, BLE, or any other wire. A later sprint binds
 * send_bytes / recv_line to a real driver.
 *
 * send_message encodes the HHIP envelope then appends '\n' (NDJSON
 * framing used by every existing sketch). receive_message takes one
 * line (with or without newline) and decodes it into an envelope.
 */

#include "hhip_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct hhip_transport {
    void *ctx;
    /* Transmit raw bytes. `bytes` is the framed line, including '\n'. */
    int (*send_bytes)(void *ctx, const char *bytes, size_t len);
    /*
     * Receive one already-framed line into buf. *out_len is the number of
     * bytes written, not counting a trailing NUL which this SDK always
     * stores when cap >= 1. Return 0 on success, non-zero on failure.
     * Returning 0 with *out_len == 0 means "no line available".
     */
    int (*recv_line)(void *ctx, char *buf, size_t cap, size_t *out_len);
} hhip_transport_t;

hhip_status_t hhip_send_message(hhip_transport_t *transport, const hhip_message_t *msg);
hhip_status_t hhip_receive_message(hhip_transport_t *transport, hhip_message_t *out);

#ifdef __cplusplus
}
#endif

#endif /* HHIP_TRANSPORT_H */
