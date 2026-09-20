#include "hhip_serial_transport.h"

static int hhip_serial_send_bytes(void *ctx, const char *bytes, size_t len)
{
    hhip_serial_transport_t *serial = (hhip_serial_transport_t *)ctx;

    if (serial == NULL || serial->uart.write == NULL) {
        return -1;
    }
    return serial->uart.write(serial->uart.ctx, bytes, len);
}

static uint32_t hhip_serial_now(const hhip_serial_transport_t *serial)
{
    if (serial->uart.millis == NULL) {
        return 0;
    }
    return serial->uart.millis(serial->uart.ctx);
}

static int hhip_serial_line_timed_out(const hhip_serial_transport_t *serial)
{
    if (serial->timeout_ms == 0U || serial->uart.millis == NULL || serial->rx_len == 0U) {
        return 0;
    }
    return (hhip_serial_now(serial) - serial->rx_started_ms) >= serial->timeout_ms ? 1 : 0;
}

static int hhip_serial_recv_line(void *ctx, char *buf, size_t cap, size_t *out_len)
{
    hhip_serial_transport_t *serial = (hhip_serial_transport_t *)ctx;

    if (serial == NULL || buf == NULL || cap == 0U || out_len == NULL) {
        return -1;
    }
    if (serial->uart.read_byte == NULL) {
        return -1;
    }

    *out_len = 0;

    if (hhip_serial_line_timed_out(serial)) {
        serial->rx_len = 0;
        return 0;
    }

    for (;;) {
        unsigned char byte = 0;
        int rc = serial->uart.read_byte(serial->uart.ctx, &byte);

        if (rc < 0) {
            serial->rx_len = 0;
            return -1;
        }

        if (rc == 1) {
            /* No more bytes this poll. Do not busy-wait — caller retries. */
            if (hhip_serial_line_timed_out(serial)) {
                serial->rx_len = 0;
            }
            return 0;
        }

        if (serial->rx_len == 0U) {
            serial->rx_started_ms = hhip_serial_now(serial);
        }

        if (byte == (unsigned char)'\r') {
            continue;
        }

        if (byte == (unsigned char)'\n') {
            if (serial->rx_len + 1U > cap) {
                serial->rx_len = 0;
                return -1;
            }
            if (serial->rx_len > 0U) {
                memcpy(buf, serial->rx_buf, serial->rx_len);
            }
            buf[serial->rx_len] = '\0';
            *out_len = serial->rx_len;
            serial->rx_len = 0;
            return 0;
        }

        if (serial->rx_len + 1U >= sizeof(serial->rx_buf)) {
            serial->rx_len = 0;
            return -1;
        }
        serial->rx_buf[serial->rx_len++] = (char)byte;
    }
}

hhip_status_t hhip_serial_transport_init(hhip_serial_transport_t *serial,
                                         const hhip_uart_hal_t *uart,
                                         uint32_t timeout_ms)
{
    if (serial == NULL || uart == NULL) {
        return HHIP_ERR_NULL;
    }
    if (uart->write == NULL || uart->read_byte == NULL) {
        return HHIP_ERR_NO_HAL;
    }

    memset(serial, 0, sizeof(*serial));
    serial->uart = *uart;
    serial->timeout_ms = timeout_ms;
    serial->transport.ctx = serial;
    serial->transport.send_bytes = hhip_serial_send_bytes;
    serial->transport.recv_line = hhip_serial_recv_line;
    return HHIP_OK;
}

hhip_status_t hhip_serial_send_message(hhip_serial_transport_t *serial,
                                       const hhip_message_t *msg)
{
    if (serial == NULL) {
        return HHIP_ERR_NULL;
    }
    return hhip_send_message(&serial->transport, msg);
}

hhip_status_t hhip_serial_receive_message(hhip_serial_transport_t *serial,
                                          hhip_message_t *out)
{
    if (serial == NULL) {
        return HHIP_ERR_NULL;
    }
    return hhip_receive_message(&serial->transport, out);
}
