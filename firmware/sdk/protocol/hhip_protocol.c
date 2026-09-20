#include "hhip_protocol.h"

#include <ctype.h>
#include <stdio.h>

#include "cJSON.h"

typedef struct hhip_type_info {
    hhip_message_type_t type;
    const char *name;
} hhip_type_info_t;

static const hhip_type_info_t k_hhip_types[] = {
    {HHIP_MSG_HELLO, HHIP_MSGTYPE_HELLO},
    {HHIP_MSG_HELLO_ACK, HHIP_MSGTYPE_HELLO_ACK},
    {HHIP_MSG_HEARTBEAT, HHIP_MSGTYPE_HEARTBEAT},
    {HHIP_MSG_READ, HHIP_MSGTYPE_READ},
    {HHIP_MSG_WRITE, HHIP_MSGTYPE_WRITE},
    {HHIP_MSG_STATE_UPDATE, HHIP_MSGTYPE_STATE_UPDATE},
    {HHIP_MSG_EVENT, HHIP_MSGTYPE_EVENT},
    {HHIP_MSG_ACK, HHIP_MSGTYPE_ACK},
    {HHIP_MSG_ERROR, HHIP_MSGTYPE_ERROR},
    {HHIP_MSG_DISCONNECT, HHIP_MSGTYPE_DISCONNECT},
    {HHIP_MSG_SYNC_REQUEST, HHIP_MSGTYPE_SYNC_REQUEST},
    {HHIP_MSG_SYNC_RESPONSE, HHIP_MSGTYPE_SYNC_RESPONSE},
    {HHIP_MSG_SYNC_CORRECTION_REQUEST, HHIP_MSGTYPE_SYNC_CORRECTION_REQUEST},
    {HHIP_MSG_SYNC_CORRECTION_RESPONSE, HHIP_MSGTYPE_SYNC_CORRECTION_RESPONSE},
};

static const char *hhip_skip_ws(const char *s)
{
    if (s == NULL) {
        return NULL;
    }
    while (*s != '\0' && isspace((unsigned char)*s)) {
        s++;
    }
    return s;
}

static hhip_status_t hhip_copy_json_text(char *dst, size_t dst_sz, const cJSON *node)
{
    char *printed;
    hhip_status_t rc;

    if (node == NULL) {
        return hhip_str_copy(dst, dst_sz, "{}");
    }
    printed = cJSON_PrintUnformatted(node);
    if (printed == NULL) {
        return HHIP_ERR_INTERNAL_ERROR;
    }
    rc = hhip_str_copy(dst, dst_sz, printed);
    cJSON_free(printed);
    return rc;
}

static int64_t hhip_json_int64(const cJSON *node, int *ok)
{
    double n;

    if (node == NULL || !cJSON_IsNumber(node)) {
        *ok = 0;
        return 0;
    }
    n = cJSON_GetNumberValue(node);
    *ok = 1;
    if (n >= 0.0) {
        return (int64_t)(n + 0.5);
    }
    return (int64_t)(n - 0.5);
}

void hhip_message_clear(hhip_message_t *msg)
{
    if (msg == NULL) {
        return;
    }
    memset(msg, 0, sizeof(*msg));
}

hhip_message_type_t hhip_message_type_from_str(const char *type)
{
    size_t i;

    if (type == NULL) {
        return HHIP_MSG_UNKNOWN;
    }
    for (i = 0; i < (sizeof k_hhip_types / sizeof k_hhip_types[0]); i++) {
        if (strcmp(type, k_hhip_types[i].name) == 0) {
            return k_hhip_types[i].type;
        }
    }
    return HHIP_MSG_UNKNOWN;
}

const char *hhip_message_type_str(hhip_message_type_t type)
{
    size_t i;

    for (i = 0; i < (sizeof k_hhip_types / sizeof k_hhip_types[0]); i++) {
        if (k_hhip_types[i].type == type) {
            return k_hhip_types[i].name;
        }
    }
    return NULL;
}

int hhip_message_type_is_known(const char *type)
{
    return hhip_message_type_from_str(type) != HHIP_MSG_UNKNOWN ? 1 : 0;
}

hhip_status_t hhip_protocol_create(hhip_message_t *msg,
                                   const char *type,
                                   const char *source,
                                   const char *target,
                                   int32_t sequence,
                                   const char *payload_json,
                                   const char *message_id,
                                   int64_t timestamp)
{
    hhip_status_t rc;
    static uint32_t s_id_counter;

    if (msg == NULL || type == NULL || source == NULL || target == NULL) {
        return HHIP_ERR_NULL;
    }

    hhip_message_clear(msg);
    msg->version = HHIP_PROTOCOL_VERSION;
    msg->sequence = sequence;
    msg->timestamp = timestamp;

    rc = hhip_str_copy(msg->type, sizeof(msg->type), type);
    if (rc != HHIP_OK) {
        return rc;
    }
    rc = hhip_str_copy(msg->source, sizeof(msg->source), source);
    if (rc != HHIP_OK) {
        return rc;
    }
    rc = hhip_str_copy(msg->target, sizeof(msg->target), target);
    if (rc != HHIP_OK) {
        return rc;
    }

    if (payload_json == NULL || payload_json[0] == '\0') {
        rc = hhip_str_copy(msg->payload_json, sizeof(msg->payload_json), "{}");
    } else {
        rc = hhip_str_copy(msg->payload_json, sizeof(msg->payload_json), payload_json);
    }
    if (rc != HHIP_OK) {
        return rc;
    }

    if (message_id != NULL && message_id[0] != '\0') {
        rc = hhip_str_copy(msg->message_id, sizeof(msg->message_id), message_id);
    } else {
        char generated[HHIP_MESSAGE_ID_MAX];
        int n;

        s_id_counter++;
        n = snprintf(generated, sizeof(generated), "%s-%lu",
                     source, (unsigned long)s_id_counter);
        if (n < 0 || (size_t)n >= sizeof(generated)) {
            return HHIP_ERR_BUFFER;
        }
        rc = hhip_str_copy(msg->message_id, sizeof(msg->message_id), generated);
    }
    if (rc != HHIP_OK) {
        return rc;
    }

    /* Populate event cache from payload if present. */
    {
        cJSON *payload = cJSON_Parse(msg->payload_json);
        const cJSON *event;

        if (payload != NULL) {
            event = cJSON_GetObjectItemCaseSensitive(payload, "event");
            if (cJSON_IsString(event) && event->valuestring != NULL) {
                (void)hhip_str_copy(msg->event, sizeof(msg->event), event->valuestring);
            }
            cJSON_Delete(payload);
        }
    }

    return HHIP_OK;
}

hhip_status_t hhip_protocol_encode(const hhip_message_t *msg, char *out, size_t out_sz)
{
    cJSON *root;
    cJSON *payload;
    char *printed;
    hhip_status_t rc;

    if (msg == NULL || out == NULL || out_sz == 0U) {
        return HHIP_ERR_NULL;
    }

    root = cJSON_CreateObject();
    if (root == NULL) {
        return HHIP_ERR_INTERNAL_ERROR;
    }

    if (cJSON_AddNumberToObject(root, "version", (double)msg->version) == NULL ||
        cJSON_AddStringToObject(root, "message_id", msg->message_id) == NULL ||
        cJSON_AddStringToObject(root, "type", msg->type) == NULL ||
        cJSON_AddStringToObject(root, "source", msg->source) == NULL ||
        cJSON_AddStringToObject(root, "target", msg->target) == NULL ||
        cJSON_AddNumberToObject(root, "sequence", (double)msg->sequence) == NULL ||
        cJSON_AddNumberToObject(root, "timestamp", (double)msg->timestamp) == NULL) {
        cJSON_Delete(root);
        return HHIP_ERR_INTERNAL_ERROR;
    }

    if (msg->payload_json[0] == '\0') {
        payload = cJSON_CreateObject();
    } else {
        payload = cJSON_Parse(msg->payload_json);
    }
    if (payload == NULL || !cJSON_IsObject(payload)) {
        cJSON_Delete(payload);
        cJSON_Delete(root);
        return HHIP_ERR_INVALID_MESSAGE;
    }
    cJSON_AddItemToObject(root, "payload", payload);

    printed = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (printed == NULL) {
        return HHIP_ERR_INTERNAL_ERROR;
    }
    rc = hhip_str_copy(out, out_sz, printed);
    cJSON_free(printed);
    return rc;
}

hhip_status_t hhip_protocol_decode(const char *line, hhip_message_t *out)
{
    const char *trimmed;
    cJSON *root;
    const cJSON *field;
    int ok;
    hhip_status_t rc;

    if (line == NULL || out == NULL) {
        return HHIP_ERR_NULL;
    }

    trimmed = hhip_skip_ws(line);
    if (trimmed == NULL || trimmed[0] == '\0') {
        return HHIP_ERR_INVALID_MESSAGE;
    }

    hhip_message_clear(out);

    root = cJSON_Parse(trimmed);
    if (root == NULL) {
        return HHIP_ERR_INVALID_MESSAGE;
    }
    if (!cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return HHIP_ERR_INVALID_MESSAGE;
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "version");
    out->version = (int)hhip_json_int64(field, &ok);
    if (!ok) {
        out->version = 0;
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "message_id");
    if (cJSON_IsString(field) && field->valuestring != NULL) {
        rc = hhip_str_copy(out->message_id, sizeof(out->message_id), field->valuestring);
        if (rc != HHIP_OK) {
            cJSON_Delete(root);
            return rc;
        }
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "type");
    if (cJSON_IsString(field) && field->valuestring != NULL) {
        rc = hhip_str_copy(out->type, sizeof(out->type), field->valuestring);
        if (rc != HHIP_OK) {
            cJSON_Delete(root);
            return rc;
        }
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "source");
    if (cJSON_IsString(field) && field->valuestring != NULL) {
        rc = hhip_str_copy(out->source, sizeof(out->source), field->valuestring);
        if (rc != HHIP_OK) {
            cJSON_Delete(root);
            return rc;
        }
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "target");
    if (cJSON_IsString(field) && field->valuestring != NULL) {
        rc = hhip_str_copy(out->target, sizeof(out->target), field->valuestring);
        if (rc != HHIP_OK) {
            cJSON_Delete(root);
            return rc;
        }
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "sequence");
    out->sequence = (int32_t)hhip_json_int64(field, &ok);
    if (!ok) {
        out->sequence = 0;
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "timestamp");
    out->timestamp = hhip_json_int64(field, &ok);
    if (!ok) {
        out->timestamp = 0;
    }

    field = cJSON_GetObjectItemCaseSensitive(root, "payload");
    if (field != NULL && !cJSON_IsObject(field)) {
        cJSON_Delete(root);
        return HHIP_ERR_INVALID_MESSAGE;
    }
    rc = hhip_copy_json_text(out->payload_json, sizeof(out->payload_json), field);
    if (rc != HHIP_OK) {
        cJSON_Delete(root);
        return rc;
    }

    if (cJSON_IsObject(field)) {
        const cJSON *event = cJSON_GetObjectItemCaseSensitive(field, "event");
        if (cJSON_IsString(event) && event->valuestring != NULL) {
            rc = hhip_str_copy(out->event, sizeof(out->event), event->valuestring);
            if (rc != HHIP_OK) {
                cJSON_Delete(root);
                return rc;
            }
        }
    }

    cJSON_Delete(root);
    return HHIP_OK;
}

hhip_status_t hhip_protocol_validate(const hhip_message_t *msg)
{
    cJSON *payload;

    if (msg == NULL) {
        return HHIP_ERR_NULL;
    }
    if (msg->version != HHIP_PROTOCOL_VERSION) {
        return HHIP_ERR_INVALID_VERSION;
    }
    if (msg->message_id[0] == '\0' || msg->source[0] == '\0' ||
        msg->target[0] == '\0' || msg->type[0] == '\0') {
        return HHIP_ERR_INVALID_MESSAGE;
    }
    if (!hhip_message_type_is_known(msg->type)) {
        return HHIP_ERR_UNKNOWN_TYPE;
    }

    payload = cJSON_Parse(msg->payload_json);
    if (payload == NULL || !cJSON_IsObject(payload)) {
        cJSON_Delete(payload);
        return HHIP_ERR_INVALID_MESSAGE;
    }
    cJSON_Delete(payload);
    return HHIP_OK;
}

int hhip_protocol_is_valid(const hhip_message_t *msg)
{
    return hhip_protocol_validate(msg) == HHIP_OK ? 1 : 0;
}

hhip_status_t hhip_dispatch(const hhip_message_t *msg,
                            const hhip_dispatch_entry_t *table,
                            size_t count,
                            void *user)
{
    size_t i;
    hhip_message_type_t type;
    const hhip_dispatch_entry_t *chosen = NULL;

    if (msg == NULL || (count > 0U && table == NULL)) {
        return HHIP_ERR_NULL;
    }

    type = hhip_message_type_from_str(msg->type);
    if (type == HHIP_MSG_UNKNOWN) {
        return HHIP_ERR_UNKNOWN_TYPE;
    }

    for (i = 0; i < count; i++) {
        if (table[i].type != type || table[i].fn == NULL) {
            continue;
        }
        if (type == HHIP_MSG_EVENT) {
            if (table[i].event == NULL) {
                if (chosen == NULL) {
                    chosen = &table[i];
                }
            } else if (strcmp(msg->event, table[i].event) == 0) {
                chosen = &table[i];
                break;
            }
        } else {
            chosen = &table[i];
            break;
        }
    }

    if (chosen == NULL) {
        return HHIP_ERR_NOT_FOUND;
    }
    if (chosen->fn(msg, user) != 0) {
        return HHIP_ERR_INTERNAL_ERROR;
    }
    return HHIP_OK;
}
