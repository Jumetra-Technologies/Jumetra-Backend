#ifndef HHIP_TYPES_H
#define HHIP_TYPES_H

/*
 * Common types for the HHIP Embedded SDK (Sprint 35).
 *
 * Portable C99: stdlib only. No Arduino, ESP-IDF, or POSIX APIs.
 */

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef HHIP_ID_MAX
#define HHIP_ID_MAX 32
#endif

#ifndef HHIP_STR_MAX
#define HHIP_STR_MAX 32
#endif

#ifndef HHIP_MESSAGE_ID_MAX
#define HHIP_MESSAGE_ID_MAX 64
#endif

#ifndef HHIP_TYPE_MAX
#define HHIP_TYPE_MAX 40
#endif

#ifndef HHIP_EVENT_MAX
#define HHIP_EVENT_MAX 40
#endif

#ifndef HHIP_PAYLOAD_MAX
#define HHIP_PAYLOAD_MAX 1024
#endif

#ifndef HHIP_ENCODE_MAX
#define HHIP_ENCODE_MAX 1536
#endif

#ifndef HHIP_LINE_MAX
#define HHIP_LINE_MAX HHIP_ENCODE_MAX
#endif

/* HHIP Protocol Version 1 — matches engine/protocol/messages.py. */
#define HHIP_PROTOCOL_VERSION 1

/*
 * Status codes. Protocol-layer names mirror ErrorCode in
 * engine/protocol/messages.py; extra values are SDK-local.
 */
typedef enum hhip_status {
    HHIP_OK = 0,
    HHIP_ERR_INVALID_MESSAGE,
    HHIP_ERR_INVALID_VERSION,
    HHIP_ERR_UNKNOWN_DEVICE,
    HHIP_ERR_INVALID_STATE,
    HHIP_ERR_TIMEOUT,
    HHIP_ERR_DUPLICATE_MESSAGE,
    HHIP_ERR_SEQUENCE_ERROR,
    HHIP_ERR_UNAUTHORIZED,
    HHIP_ERR_INTERNAL_ERROR,
    HHIP_ERR_NULL,
    HHIP_ERR_BUFFER,
    HHIP_ERR_NO_TRANSPORT,
    HHIP_ERR_NO_HAL,
    HHIP_ERR_UNKNOWN_TYPE,
    HHIP_ERR_NOT_FOUND
} hhip_status_t;

/* Wire strings for ERROR payloads — identical to Python ErrorCode. */
#define HHIP_ERROR_INVALID_MESSAGE "INVALID_MESSAGE"
#define HHIP_ERROR_INVALID_VERSION "INVALID_VERSION"
#define HHIP_ERROR_UNKNOWN_DEVICE "UNKNOWN_DEVICE"
#define HHIP_ERROR_INVALID_STATE "INVALID_STATE"
#define HHIP_ERROR_TIMEOUT "TIMEOUT"
#define HHIP_ERROR_DUPLICATE_MESSAGE "DUPLICATE_MESSAGE"
#define HHIP_ERROR_SEQUENCE_ERROR "SEQUENCE_ERROR"
#define HHIP_ERROR_UNAUTHORIZED "UNAUTHORIZED"
#define HHIP_ERROR_INTERNAL_ERROR "INTERNAL_ERROR"

static inline hhip_status_t hhip_str_copy(char *dst, size_t dst_sz, const char *src)
{
    size_t n;

    if (dst == NULL || dst_sz == 0U) {
        return HHIP_ERR_NULL;
    }
    if (src == NULL) {
        src = "";
    }
    n = strlen(src);
    if (n >= dst_sz) {
        return HHIP_ERR_BUFFER;
    }
    memcpy(dst, src, n + 1U);
    return HHIP_OK;
}

static inline void hhip_str_clear(char *dst, size_t dst_sz)
{
    if (dst != NULL && dst_sz > 0U) {
        dst[0] = '\0';
    }
}

#ifdef __cplusplus
}
#endif

#endif /* HHIP_TYPES_H */
