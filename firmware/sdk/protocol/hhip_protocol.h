#ifndef HHIP_PROTOCOL_H
#define HHIP_PROTOCOL_H

/*
 * HHIP Protocol Version 1 envelope — portable C (stdlib + cJSON).
 *
 * Source of truth for the wire format: engine/protocol/messages.py.
 * This module is the SDK-side port of that envelope (the cited
 * firmware/hhip_protocol.c was not present in the tree). Envelope
 * fields, MessageType constants, and the EVENT / payload.event
 * sub-dispatch pattern are unchanged.
 *
 * Two message-type generations coexist on this envelope:
 *   Generation 1 (hhip_device, sync_agent): type is HELLO / HEARTBEAT /
 *     WRITE / STATE_UPDATE / SYNC_* etc.
 *   Generation 2 (hhip_agent ESP32/Uno, raspberry agent): type is EVENT
 *     and payload.event is DEVICE_DISCOVERY / GPIO_STATE / GPIO_WRITE.
 *
 * Encoding does not append a newline. Framing belongs to transport
 * (hhip_send_message), matching encode_message() in messages.py.
 */

#include "hhip_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define HHIP_MSGTYPE_HELLO "HELLO"
#define HHIP_MSGTYPE_HELLO_ACK "HELLO_ACK"
#define HHIP_MSGTYPE_HEARTBEAT "HEARTBEAT"
#define HHIP_MSGTYPE_READ "READ"
#define HHIP_MSGTYPE_WRITE "WRITE"
#define HHIP_MSGTYPE_STATE_UPDATE "STATE_UPDATE"
#define HHIP_MSGTYPE_EVENT "EVENT"
#define HHIP_MSGTYPE_ACK "ACK"
#define HHIP_MSGTYPE_ERROR "ERROR"
#define HHIP_MSGTYPE_DISCONNECT "DISCONNECT"
#define HHIP_MSGTYPE_SYNC_REQUEST "SYNC_REQUEST"
#define HHIP_MSGTYPE_SYNC_RESPONSE "SYNC_RESPONSE"
#define HHIP_MSGTYPE_SYNC_CORRECTION_REQUEST "SYNC_CORRECTION_REQUEST"
#define HHIP_MSGTYPE_SYNC_CORRECTION_RESPONSE "SYNC_CORRECTION_RESPONSE"

#define HHIP_EVENT_DEVICE_DISCOVERY "DEVICE_DISCOVERY"
#define HHIP_EVENT_GPIO_STATE "GPIO_STATE"
#define HHIP_EVENT_GPIO_WRITE "GPIO_WRITE"

typedef enum hhip_message_type {
    HHIP_MSG_UNKNOWN = 0,
    HHIP_MSG_HELLO,
    HHIP_MSG_HELLO_ACK,
    HHIP_MSG_HEARTBEAT,
    HHIP_MSG_READ,
    HHIP_MSG_WRITE,
    HHIP_MSG_STATE_UPDATE,
    HHIP_MSG_EVENT,
    HHIP_MSG_ACK,
    HHIP_MSG_ERROR,
    HHIP_MSG_DISCONNECT,
    HHIP_MSG_SYNC_REQUEST,
    HHIP_MSG_SYNC_RESPONSE,
    HHIP_MSG_SYNC_CORRECTION_REQUEST,
    HHIP_MSG_SYNC_CORRECTION_RESPONSE
} hhip_message_type_t;

typedef struct hhip_message {
    int version;
    char message_id[HHIP_MESSAGE_ID_MAX];
    char type[HHIP_TYPE_MAX];
    char source[HHIP_ID_MAX];
    char target[HHIP_ID_MAX];
    int32_t sequence;
    int64_t timestamp;
    char payload_json[HHIP_PAYLOAD_MAX];
    char event[HHIP_EVENT_MAX]; /* payload.event when present; else empty */
} hhip_message_t;

typedef int (*hhip_handler_fn)(const hhip_message_t *msg, void *user);

/*
 * Dispatch table bridging the two generations. For non-EVENT types,
 * `event` must be NULL. For EVENT rows, `event` is payload.event
 * (e.g. "GPIO_WRITE"). A NULL event on an EVENT row matches any event.
 */
typedef struct hhip_dispatch_entry {
    hhip_message_type_t type;
    const char *event;
    hhip_handler_fn fn;
} hhip_dispatch_entry_t;

void hhip_message_clear(hhip_message_t *msg);

hhip_message_type_t hhip_message_type_from_str(const char *type);
const char *hhip_message_type_str(hhip_message_type_t type);
int hhip_message_type_is_known(const char *type);

hhip_status_t hhip_protocol_create(hhip_message_t *msg,
                                   const char *type,
                                   const char *source,
                                   const char *target,
                                   int32_t sequence,
                                   const char *payload_json,
                                   const char *message_id,
                                   int64_t timestamp);

/* Encode to a single-line JSON object. Does not append '\n'. */
hhip_status_t hhip_protocol_encode(const hhip_message_t *msg,
                                   char *out,
                                   size_t out_sz);

/*
 * Decode one NDJSON line (trailing newline optional). Does not run
 * protocol-level validation — use hhip_protocol_validate().
 */
hhip_status_t hhip_protocol_decode(const char *line, hhip_message_t *out);

hhip_status_t hhip_protocol_validate(const hhip_message_t *msg);

int hhip_protocol_is_valid(const hhip_message_t *msg);

hhip_status_t hhip_dispatch(const hhip_message_t *msg,
                            const hhip_dispatch_entry_t *table,
                            size_t count,
                            void *user);

#ifdef __cplusplus
}
#endif

#endif /* HHIP_PROTOCOL_H */
