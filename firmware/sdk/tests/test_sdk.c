/*
 * HHIP Embedded SDK unit tests (Sprint 35).
 *
 * Pattern: real sample lines, explicit assertions, compiled and run
 * with -Wall -Wextra -Werror plus AddressSanitizer (and LeakSanitizer
 * when the toolchain provides it). Same spirit as the cited
 * firmware/test_bridge.c approach.
 */

#include "hhip_sdk.h"
#include "cJSON.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_cjson_allocs;
static int g_cjson_frees;

static void *CJSON_CDECL test_cjson_malloc(size_t sz)
{
    void *p = malloc(sz);
    if (p != NULL) {
        g_cjson_allocs++;
    }
    return p;
}

static void CJSON_CDECL test_cjson_free(void *p)
{
    if (p != NULL) {
        g_cjson_frees++;
    }
    free(p);
}

static int g_pass;
static int g_fail;

#define ASSERT_TRUE(cond)                                                          \
    do {                                                                           \
        if (cond) {                                                                \
            g_pass++;                                                              \
        } else {                                                                   \
            g_fail++;                                                              \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);        \
        }                                                                          \
    } while (0)

#define ASSERT_EQ_INT(a, b)                                                        \
    do {                                                                           \
        long long _va = (long long)(a);                                            \
        long long _vb = (long long)(b);                                            \
        if (_va == _vb) {                                                          \
            g_pass++;                                                              \
        } else {                                                                   \
            g_fail++;                                                              \
            fprintf(stderr, "FAIL %s:%d: %s == %s (%lld != %lld)\n",               \
                    __FILE__, __LINE__, #a, #b, _va, _vb);                         \
        }                                                                          \
    } while (0)

#define ASSERT_STREQ(a, b)                                                         \
    do {                                                                           \
        const char *_sa = (a);                                                     \
        const char *_sb = (b);                                                     \
        if (_sa != NULL && _sb != NULL && strcmp(_sa, _sb) == 0) {                 \
            g_pass++;                                                              \
        } else {                                                                   \
            g_fail++;                                                              \
            fprintf(stderr, "FAIL %s:%d: %s == %s (%s != %s)\n",                   \
                    __FILE__, __LINE__, #a, #b,                                    \
                    _sa ? _sa : "(null)", _sb ? _sb : "(null)");                   \
        }                                                                          \
    } while (0)

/* Real PoC-01 envelope from docs/poc-01.md (required fields, empty payload). */
static const char k_sample_hello[] =
    "{\"version\":1,\"message_id\":\"unique-id\",\"type\":\"HELLO\","
    "\"source\":\"esp32_01\",\"target\":\"hhip\",\"sequence\":1,"
    "\"timestamp\":1723456789123,\"payload\":{}}";

/* Generation 1 HELLO with payload, matching firmware/esp32/hhip_device. */
static const char k_sample_hello_payload[] =
    "{\"version\":1,\"message_id\":\"esp32_01-1\",\"type\":\"HELLO\","
    "\"source\":\"esp32_01\",\"target\":\"hhip\",\"sequence\":1,"
    "\"timestamp\":42,\"payload\":{\"device_type\":\"esp32\","
    "\"firmware_version\":\"0.2.0\"}}";

/* Generation 2 EVENT / DEVICE_DISCOVERY, matching hhip_agent sketches. */
static const char k_sample_discovery[] =
    "{\"version\":1,\"message_id\":\"esp32_AABB-1\",\"type\":\"EVENT\","
    "\"source\":\"esp32_AABB\",\"target\":\"hhip\",\"sequence\":1,"
    "\"timestamp\":100,\"payload\":{\"event\":\"DEVICE_DISCOVERY\","
    "\"device_id\":\"esp32_AABB\",\"board_type\":\"esp32\","
    "\"firmware_version\":\"1.0.0-hhip-agent\","
    "\"capabilities\":[\"gpio\",\"pwm\",\"adc\"]}}";

/* Generation 2 EVENT / GPIO_WRITE. */
static const char k_sample_gpio_write[] =
    "{\"version\":1,\"message_id\":\"hhip-9\",\"type\":\"EVENT\","
    "\"source\":\"hhip\",\"target\":\"esp32_AABB\",\"sequence\":9,"
    "\"timestamp\":200,\"payload\":{\"event\":\"GPIO_WRITE\","
    "\"pin\":\"D13\",\"value\":1}}";

/* Generation 1 WRITE (hhip_device / agent WRITE path). */
static const char k_sample_write[] =
    "{\"version\":1,\"message_id\":\"hhip-10\",\"type\":\"WRITE\","
    "\"source\":\"hhip\",\"target\":\"esp32_01\",\"sequence\":10,"
    "\"timestamp\":201,\"payload\":{\"pin\":\"D13\",\"value\":1}}";

/* HEARTBEAT with empty payload object. */
static const char k_sample_heartbeat[] =
    "{\"version\":1,\"message_id\":\"esp32_01-2\",\"type\":\"HEARTBEAT\","
    "\"source\":\"esp32_01\",\"target\":\"hhip\",\"sequence\":2,"
    "\"timestamp\":5000,\"payload\":{}}";

/* SYNC_REQUEST envelope from the Sprint 16 sync agent path. */
static const char k_sample_sync_request[] =
    "{\"version\":1,\"message_id\":\"sync-1\",\"type\":\"SYNC_REQUEST\","
    "\"source\":\"hhip\",\"target\":\"esp32_01\",\"sequence\":1,"
    "\"timestamp\":1000,\"payload\":{\"request_id\":\"r1\","
    "\"sequence_number\":1,\"device_id\":\"esp32_01\","
    "\"server_timestamp\":1000,\"device_timestamp\":0,"
    "\"correlation_id\":\"c1\"}}";

static void test_device_init(void)
{
    hhip_device_t dev;
    hhip_device_config_t cfg;
    hhip_device_config_t bad;

    memset(&cfg, 0, sizeof(cfg));
    cfg.device_id = "esp32_01";
    cfg.manufacturer = "Espressif";
    cfg.model = "ESP32-WROOM-32";
    cfg.firmware_version = "1.0.0-hhip-sdk";
    cfg.board_type = "esp32";

    ASSERT_EQ_INT(hhip_device_init(&dev, &cfg), HHIP_OK);
    ASSERT_STREQ(dev.device_id, "esp32_01");
    ASSERT_STREQ(dev.manufacturer, "Espressif");
    ASSERT_STREQ(dev.model, "ESP32-WROOM-32");
    ASSERT_STREQ(dev.firmware_version, "1.0.0-hhip-sdk");
    ASSERT_STREQ(dev.board_type, "esp32");
    ASSERT_EQ_INT(dev.capabilities, 0);
    ASSERT_EQ_INT(dev.lifecycle_state, HHIP_LIFE_BOOTING);

    memset(&bad, 0, sizeof(bad));
    bad.device_id = "";
    bad.board_type = "esp32";
    ASSERT_EQ_INT(hhip_device_init(&dev, &bad), HHIP_ERR_INVALID_MESSAGE);

    bad.device_id = "esp32_01";
    bad.board_type = NULL;
    ASSERT_EQ_INT(hhip_device_init(&dev, &bad), HHIP_ERR_INVALID_MESSAGE);
    ASSERT_EQ_INT(hhip_device_init(NULL, &cfg), HHIP_ERR_NULL);
}

static void test_capability_registration(void)
{
    hhip_device_t dev;
    hhip_device_config_t cfg;

    memset(&cfg, 0, sizeof(cfg));
    cfg.device_id = "stm32_01";
    cfg.board_type = "stm32";
    ASSERT_EQ_INT(hhip_device_init(&dev, &cfg), HHIP_OK);

    ASSERT_EQ_INT(hhip_device_register_capability(&dev, HHIP_CAP_GPIO), HHIP_OK);
    ASSERT_EQ_INT(hhip_device_register_capability(&dev, HHIP_CAP_ADC), HHIP_OK);
    ASSERT_EQ_INT(hhip_capabilities_register_name(&dev.capabilities, "pwm"), HHIP_OK);
    ASSERT_EQ_INT(hhip_capabilities_register_name(&dev.capabilities, "I2C"), HHIP_OK);

    ASSERT_TRUE(hhip_capabilities_has(dev.capabilities, HHIP_CAP_GPIO));
    ASSERT_TRUE(hhip_capabilities_has(dev.capabilities, HHIP_CAP_ADC));
    ASSERT_TRUE(hhip_capabilities_has(dev.capabilities, HHIP_CAP_PWM));
    ASSERT_TRUE(hhip_capabilities_has(dev.capabilities, HHIP_CAP_I2C));
    ASSERT_TRUE(!hhip_capabilities_has(dev.capabilities, HHIP_CAP_SPI));
    ASSERT_TRUE(!hhip_capabilities_has(dev.capabilities, HHIP_CAP_CAN));

    /* Forward-looking industrial caps are registrable on the device. */
    ASSERT_EQ_INT(hhip_device_register_capability(&dev, HHIP_CAP_CAN), HHIP_OK);
    ASSERT_EQ_INT(hhip_device_register_capability(&dev, HHIP_CAP_MODBUS), HHIP_OK);
    ASSERT_EQ_INT(hhip_device_register_capability(&dev, HHIP_CAP_ETHERNET), HHIP_OK);
    ASSERT_TRUE(hhip_capabilities_has(dev.capabilities, HHIP_CAP_CAN));
    ASSERT_STREQ(hhip_capability_name(HHIP_CAP_GPIO), "GPIO");
    ASSERT_STREQ(hhip_capability_wire_name(HHIP_CAP_GPIO), "gpio");

    ASSERT_EQ_INT(hhip_capabilities_register(&dev.capabilities, (hhip_capability_t)0),
                  HHIP_ERR_NOT_FOUND);
    ASSERT_EQ_INT(hhip_capabilities_register_name(&dev.capabilities, "wifi"),
                  HHIP_ERR_NOT_FOUND);
    ASSERT_EQ_INT(hhip_capabilities_register(&dev.capabilities,
                                             (hhip_capability_t)(HHIP_CAP_GPIO | HHIP_CAP_ADC)),
                  HHIP_ERR_NOT_FOUND);
}

static void test_lifecycle_valid(void)
{
    hhip_lifecycle_state_t state = HHIP_LIFE_BOOTING;

    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_DISCOVERING), HHIP_OK);
    ASSERT_EQ_INT(state, HHIP_LIFE_DISCOVERING);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_CONNECTING), HHIP_OK);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_CONNECTED), HHIP_OK);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_SYNCING), HHIP_OK);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_RUNNING), HHIP_OK);
    ASSERT_STREQ(hhip_lifecycle_name(state), "RUNNING");

    /* Optional skip of SYNCING: CONNECTED -> RUNNING */
    state = HHIP_LIFE_CONNECTED;
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_RUNNING), HHIP_OK);

    /* Update path: RUNNING -> UPDATING -> BOOTING */
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_UPDATING), HHIP_OK);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_BOOTING), HHIP_OK);

    /* Recovery: ERROR -> DISCOVERING */
    state = HHIP_LIFE_RUNNING;
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_ERROR), HHIP_OK);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_DISCOVERING), HHIP_OK);
}

static void test_lifecycle_invalid(void)
{
    hhip_lifecycle_state_t state = HHIP_LIFE_BOOTING;

    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_RUNNING), HHIP_ERR_INVALID_STATE);
    ASSERT_EQ_INT(state, HHIP_LIFE_BOOTING);

    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_CONNECTED), HHIP_ERR_INVALID_STATE);
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_BOOTING), HHIP_ERR_INVALID_STATE);

    state = HHIP_LIFE_DISCOVERING;
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_RUNNING), HHIP_ERR_INVALID_STATE);
    ASSERT_EQ_INT(state, HHIP_LIFE_DISCOVERING);

    state = HHIP_LIFE_ERROR;
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_RUNNING), HHIP_ERR_INVALID_STATE);
    ASSERT_EQ_INT(state, HHIP_LIFE_ERROR);

    state = HHIP_LIFE_UPDATING;
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_CONNECTED), HHIP_ERR_INVALID_STATE);
    ASSERT_EQ_INT(state, HHIP_LIFE_UPDATING);

    state = HHIP_LIFE_RUNNING;
    ASSERT_EQ_INT(hhip_lifecycle_transition(&state, HHIP_LIFE_BOOTING), HHIP_ERR_INVALID_STATE);
    ASSERT_EQ_INT(state, HHIP_LIFE_RUNNING);

    ASSERT_EQ_INT(hhip_lifecycle_transition(NULL, HHIP_LIFE_ERROR), HHIP_ERR_NULL);
    ASSERT_TRUE(!hhip_lifecycle_is_allowed(HHIP_LIFE_BOOTING, HHIP_LIFE_SYNCING));
}

static void assert_roundtrip_line(const char *line)
{
    hhip_message_t decoded;
    hhip_message_t again;
    char encoded[HHIP_ENCODE_MAX];

    ASSERT_EQ_INT(hhip_protocol_decode(line, &decoded), HHIP_OK);
    ASSERT_EQ_INT(hhip_protocol_validate(&decoded), HHIP_OK);
    ASSERT_EQ_INT(hhip_protocol_encode(&decoded, encoded, sizeof(encoded)), HHIP_OK);
    ASSERT_TRUE(encoded[0] != '\0');
    ASSERT_TRUE(encoded[strlen(encoded) - 1U] != '\n');
    ASSERT_EQ_INT(hhip_protocol_decode(encoded, &again), HHIP_OK);

    ASSERT_EQ_INT(again.version, decoded.version);
    ASSERT_STREQ(again.message_id, decoded.message_id);
    ASSERT_STREQ(again.type, decoded.type);
    ASSERT_STREQ(again.source, decoded.source);
    ASSERT_STREQ(again.target, decoded.target);
    ASSERT_EQ_INT(again.sequence, decoded.sequence);
    ASSERT_EQ_INT(again.timestamp, decoded.timestamp);
    ASSERT_STREQ(again.event, decoded.event);
    ASSERT_STREQ(again.payload_json, decoded.payload_json);
}

static void test_protocol_roundtrip(void)
{
    hhip_message_t hello;
    hhip_message_t created;
    char encoded[HHIP_ENCODE_MAX];

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_hello, &hello), HHIP_OK);
    ASSERT_EQ_INT(hello.version, 1);
    ASSERT_STREQ(hello.message_id, "unique-id");
    ASSERT_STREQ(hello.type, HHIP_MSGTYPE_HELLO);
    ASSERT_STREQ(hello.source, "esp32_01");
    ASSERT_STREQ(hello.target, "hhip");
    ASSERT_EQ_INT(hello.sequence, 1);
    ASSERT_EQ_INT(hello.timestamp, 1723456789123LL);
    ASSERT_STREQ(hello.payload_json, "{}");
    ASSERT_TRUE(hhip_protocol_is_valid(&hello));

    ASSERT_EQ_INT(hhip_protocol_encode(&hello, encoded, sizeof(encoded)), HHIP_OK);
    ASSERT_STREQ(encoded, k_sample_hello);

    assert_roundtrip_line(k_sample_hello);
    assert_roundtrip_line(k_sample_hello_payload);
    assert_roundtrip_line(k_sample_discovery);
    assert_roundtrip_line(k_sample_gpio_write);
    assert_roundtrip_line(k_sample_write);
    assert_roundtrip_line(k_sample_heartbeat);
    assert_roundtrip_line(k_sample_sync_request);

    ASSERT_EQ_INT(hhip_protocol_create(&created,
                                       HHIP_MSGTYPE_ACK,
                                       "hhip",
                                       "esp32_01",
                                       3,
                                       "{}",
                                       "fixed-id",
                                       1234),
                  HHIP_OK);
    ASSERT_EQ_INT(hhip_protocol_encode(&created, encoded, sizeof(encoded)), HHIP_OK);
    ASSERT_TRUE(strstr(encoded, "\"type\":\"ACK\"") != NULL);
    ASSERT_TRUE(strstr(encoded, "\"message_id\":\"fixed-id\"") != NULL);
    ASSERT_TRUE(encoded[strlen(encoded) - 1U] != '\n');
}

static void test_protocol_errors(void)
{
    hhip_message_t msg;

    ASSERT_EQ_INT(hhip_protocol_decode("", &msg), HHIP_ERR_INVALID_MESSAGE);
    ASSERT_EQ_INT(hhip_protocol_decode("   \n", &msg), HHIP_ERR_INVALID_MESSAGE);
    ASSERT_EQ_INT(hhip_protocol_decode("{not valid json", &msg), HHIP_ERR_INVALID_MESSAGE);
    ASSERT_EQ_INT(hhip_protocol_decode("[1,2,3]", &msg), HHIP_ERR_INVALID_MESSAGE);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_hello, &msg), HHIP_OK);
    (void)hhip_str_copy(msg.type, sizeof(msg.type), "NOT_A_REAL_TYPE");
    ASSERT_EQ_INT(hhip_protocol_validate(&msg), HHIP_ERR_UNKNOWN_TYPE);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_hello, &msg), HHIP_OK);
    msg.version = 99;
    ASSERT_EQ_INT(hhip_protocol_validate(&msg), HHIP_ERR_INVALID_VERSION);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_hello, &msg), HHIP_OK);
    msg.source[0] = '\0';
    ASSERT_EQ_INT(hhip_protocol_validate(&msg), HHIP_ERR_INVALID_MESSAGE);

    ASSERT_TRUE(hhip_message_type_is_known(HHIP_MSGTYPE_SYNC_CORRECTION_RESPONSE));
    ASSERT_TRUE(!hhip_message_type_is_known("GPIO_WRITE")); /* EVENT sub-type, not MessageType */
}

typedef struct dispatch_log {
    int hello;
    int gpio_write;
    int write;
    int discovery;
} dispatch_log_t;

static int on_hello(const hhip_message_t *msg, void *user)
{
    dispatch_log_t *log = (dispatch_log_t *)user;
    (void)msg;
    log->hello++;
    return 0;
}

static int on_gpio_write(const hhip_message_t *msg, void *user)
{
    dispatch_log_t *log = (dispatch_log_t *)user;
    ASSERT_STREQ(msg->event, HHIP_EVENT_GPIO_WRITE);
    log->gpio_write++;
    return 0;
}

static int on_write(const hhip_message_t *msg, void *user)
{
    dispatch_log_t *log = (dispatch_log_t *)user;
    (void)msg;
    log->write++;
    return 0;
}

static int on_discovery(const hhip_message_t *msg, void *user)
{
    dispatch_log_t *log = (dispatch_log_t *)user;
    ASSERT_STREQ(msg->event, HHIP_EVENT_DEVICE_DISCOVERY);
    log->discovery++;
    return 0;
}

static void test_dispatch_two_generations(void)
{
    hhip_message_t msg;
    dispatch_log_t log;
    const hhip_dispatch_entry_t table[] = {
        {HHIP_MSG_HELLO, NULL, on_hello},
        {HHIP_MSG_WRITE, NULL, on_write},
        {HHIP_MSG_EVENT, HHIP_EVENT_GPIO_WRITE, on_gpio_write},
        {HHIP_MSG_EVENT, HHIP_EVENT_DEVICE_DISCOVERY, on_discovery},
    };

    memset(&log, 0, sizeof(log));

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_hello, &msg), HHIP_OK);
    ASSERT_EQ_INT(hhip_dispatch(&msg, table, sizeof table / sizeof table[0], &log), HHIP_OK);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_gpio_write, &msg), HHIP_OK);
    ASSERT_EQ_INT(hhip_dispatch(&msg, table, sizeof table / sizeof table[0], &log), HHIP_OK);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_write, &msg), HHIP_OK);
    ASSERT_EQ_INT(hhip_dispatch(&msg, table, sizeof table / sizeof table[0], &log), HHIP_OK);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_discovery, &msg), HHIP_OK);
    ASSERT_EQ_INT(hhip_dispatch(&msg, table, sizeof table / sizeof table[0], &log), HHIP_OK);

    ASSERT_EQ_INT(log.hello, 1);
    ASSERT_EQ_INT(log.gpio_write, 1);
    ASSERT_EQ_INT(log.write, 1);
    ASSERT_EQ_INT(log.discovery, 1);

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_heartbeat, &msg), HHIP_OK);
    ASSERT_EQ_INT(hhip_dispatch(&msg, table, sizeof table / sizeof table[0], &log),
                  HHIP_ERR_NOT_FOUND);
}

typedef struct loopback {
    char line[HHIP_LINE_MAX];
    size_t len;
    int occupied;
} loopback_t;

static int loopback_send(void *ctx, const char *bytes, size_t len)
{
    loopback_t *lb = (loopback_t *)ctx;

    if (len >= sizeof(lb->line)) {
        return -1;
    }
    memcpy(lb->line, bytes, len);
    lb->line[len] = '\0';
    lb->len = len;
    lb->occupied = 1;
    return 0;
}

static int loopback_recv(void *ctx, char *buf, size_t cap, size_t *out_len)
{
    loopback_t *lb = (loopback_t *)ctx;

    if (!lb->occupied) {
        *out_len = 0;
        return 0;
    }
    if (lb->len + 1U > cap) {
        return -1;
    }
    memcpy(buf, lb->line, lb->len + 1U);
    *out_len = lb->len;
    lb->occupied = 0;
    return 0;
}

static void test_transport_loopback(void)
{
    loopback_t lb;
    hhip_transport_t t;
    hhip_message_t out;
    hhip_message_t in;

    memset(&lb, 0, sizeof(lb));
    memset(&t, 0, sizeof(t));
    t.ctx = &lb;
    t.send_bytes = loopback_send;
    t.recv_line = loopback_recv;

    ASSERT_EQ_INT(hhip_protocol_decode(k_sample_gpio_write, &out), HHIP_OK);
    ASSERT_EQ_INT(hhip_send_message(&t, &out), HHIP_OK);
    ASSERT_TRUE(lb.occupied);
    ASSERT_TRUE(lb.len > 0U);
    ASSERT_EQ_INT((int)lb.line[lb.len - 1U], (int)'\n');

    ASSERT_EQ_INT(hhip_receive_message(&t, &in), HHIP_OK);
    ASSERT_STREQ(in.type, HHIP_MSGTYPE_EVENT);
    ASSERT_STREQ(in.event, HHIP_EVENT_GPIO_WRITE);
    ASSERT_STREQ(in.source, "hhip");
    ASSERT_EQ_INT(in.sequence, 9);
}

static int mock_gpio_write(void *ctx, int pin, int value)
{
    int *store = (int *)ctx;
    (void)pin;
    *store = value;
    return 0;
}

static int mock_gpio_read(void *ctx, int pin, int *out_value)
{
    int *store = (int *)ctx;
    (void)pin;
    *out_value = *store;
    return 0;
}

static int mock_pwm_write(void *ctx, int pin, unsigned duty, unsigned freq_hz)
{
    (void)ctx;
    (void)pin;
    (void)duty;
    (void)freq_hz;
    return 0;
}

static int mock_analog_read(void *ctx, int pin, int *out_value)
{
    (void)ctx;
    (void)pin;
    *out_value = 123;
    return 0;
}

static void test_hal_interfaces(void)
{
    hhip_hal_t hal;
    int pin_value = 0;
    int read_back = -1;
    int analog = -1;

    memset(&hal, 0, sizeof(hal));
    ASSERT_EQ_INT(hhip_hal_gpio_write(&hal, 13, 1), HHIP_ERR_NO_HAL);

    hal.ctx = &pin_value;
    hal.gpio_write = mock_gpio_write;
    hal.gpio_read = mock_gpio_read;
    hal.pwm_write = mock_pwm_write;
    hal.analog_read = mock_analog_read;

    ASSERT_EQ_INT(hhip_hal_gpio_write(&hal, 13, 1), HHIP_OK);
    ASSERT_EQ_INT(hhip_hal_gpio_read(&hal, 13, &read_back), HHIP_OK);
    ASSERT_EQ_INT(read_back, 1);
    ASSERT_EQ_INT(hhip_hal_pwm_write(&hal, 5, 128, 1000), HHIP_OK);
    ASSERT_EQ_INT(hhip_hal_analog_read(&hal, 0, &analog), HHIP_OK);
    ASSERT_EQ_INT(analog, 123);
}

int main(void)
{
    cJSON_Hooks hooks;

    memset(&hooks, 0, sizeof(hooks));
    hooks.malloc_fn = test_cjson_malloc;
    hooks.free_fn = test_cjson_free;
    cJSON_InitHooks(&hooks);

    test_device_init();
    test_capability_registration();
    test_lifecycle_valid();
    test_lifecycle_invalid();
    test_protocol_roundtrip();
    test_protocol_errors();
    test_dispatch_two_generations();
    test_transport_loopback();
    test_hal_interfaces();

    ASSERT_TRUE(g_cjson_allocs > 0);
    ASSERT_EQ_INT(g_cjson_allocs, g_cjson_frees);
    printf("cjson heap: %d alloc, %d free, outstanding %d\n",
           g_cjson_allocs, g_cjson_frees, g_cjson_allocs - g_cjson_frees);
    printf("hhip sdk tests: %d passed, %d failed\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
