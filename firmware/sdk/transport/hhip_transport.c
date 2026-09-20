#include "hhip_transport.h"

hhip_status_t hhip_send_message(hhip_transport_t *transport, const hhip_message_t *msg)
{
    char line[HHIP_ENCODE_MAX];
    size_t len;
    hhip_status_t rc;

    if (transport == NULL || msg == NULL) {
        return HHIP_ERR_NULL;
    }
    if (transport->send_bytes == NULL) {
        return HHIP_ERR_NO_TRANSPORT;
    }

    rc = hhip_protocol_encode(msg, line, sizeof(line) - 1U);
    if (rc != HHIP_OK) {
        return rc;
    }

    len = strlen(line);
    line[len] = '\n';
    line[len + 1U] = '\0';

    if (transport->send_bytes(transport->ctx, line, len + 1U) != 0) {
        return HHIP_ERR_INTERNAL_ERROR;
    }
    return HHIP_OK;
}

hhip_status_t hhip_receive_message(hhip_transport_t *transport, hhip_message_t *out)
{
    char line[HHIP_LINE_MAX];
    size_t n = 0;
    hhip_status_t rc;

    if (transport == NULL || out == NULL) {
        return HHIP_ERR_NULL;
    }
    if (transport->recv_line == NULL) {
        return HHIP_ERR_NO_TRANSPORT;
    }

    if (transport->recv_line(transport->ctx, line, sizeof(line), &n) != 0) {
        return HHIP_ERR_INTERNAL_ERROR;
    }
    if (n == 0U) {
        return HHIP_ERR_TIMEOUT;
    }

    rc = hhip_protocol_decode(line, out);
    if (rc != HHIP_OK) {
        return rc;
    }
    return hhip_protocol_validate(out);
}
