#include "hhip_capabilities.h"

#include <ctype.h>

typedef struct hhip_cap_info {
    hhip_capability_t cap;
    const char *name;
    const char *wire;
} hhip_cap_info_t;

static const hhip_cap_info_t k_hhip_caps[] = {
    {HHIP_CAP_GPIO,     "GPIO",     "gpio"},
    {HHIP_CAP_ADC,      "ADC",      "adc"},
    {HHIP_CAP_PWM,      "PWM",      "pwm"},
    {HHIP_CAP_SPI,      "SPI",      "spi"},
    {HHIP_CAP_I2C,      "I2C",      "i2c"},
    {HHIP_CAP_UART,     "UART",     "uart"},
    {HHIP_CAP_CAN,      "CAN",      "can"},
    {HHIP_CAP_MODBUS,   "MODBUS",   "modbus"},
    {HHIP_CAP_ETHERNET, "ETHERNET", "ethernet"},
};

static int hhip_ascii_ieq(const char *a, const char *b)
{
    unsigned char ca;
    unsigned char cb;

    if (a == NULL || b == NULL) {
        return 0;
    }
    while (*a != '\0' && *b != '\0') {
        ca = (unsigned char)*a;
        cb = (unsigned char)*b;
        if (tolower(ca) != tolower(cb)) {
            return 0;
        }
        a++;
        b++;
    }
    return (*a == '\0' && *b == '\0') ? 1 : 0;
}

static const hhip_cap_info_t *hhip_cap_lookup(hhip_capability_t cap)
{
    size_t i;

    for (i = 0; i < (sizeof k_hhip_caps / sizeof k_hhip_caps[0]); i++) {
        if (k_hhip_caps[i].cap == cap) {
            return &k_hhip_caps[i];
        }
    }
    return NULL;
}

hhip_status_t hhip_capabilities_register(hhip_capability_mask_t *set,
                                         hhip_capability_t cap)
{
    if (set == NULL) {
        return HHIP_ERR_NULL;
    }
    if (cap == 0 || (cap & ~HHIP_CAP_KNOWN_MASK) != 0 || (cap & (cap - 1u)) != 0u) {
        /* Reject zero, unknown bits, and multi-bit values. */
        return HHIP_ERR_NOT_FOUND;
    }
    *set |= (hhip_capability_mask_t)cap;
    return HHIP_OK;
}

hhip_status_t hhip_capabilities_register_name(hhip_capability_mask_t *set,
                                              const char *name)
{
    hhip_capability_t cap;

    cap = hhip_capability_from_name(name);
    if (cap == 0) {
        return HHIP_ERR_NOT_FOUND;
    }
    return hhip_capabilities_register(set, cap);
}

int hhip_capabilities_has(hhip_capability_mask_t set, hhip_capability_t cap)
{
    return (set & (hhip_capability_mask_t)cap) != 0u ? 1 : 0;
}

const char *hhip_capability_name(hhip_capability_t cap)
{
    const hhip_cap_info_t *info;

    info = hhip_cap_lookup(cap);
    return info != NULL ? info->name : NULL;
}

const char *hhip_capability_wire_name(hhip_capability_t cap)
{
    const hhip_cap_info_t *info;

    info = hhip_cap_lookup(cap);
    return info != NULL ? info->wire : NULL;
}

hhip_capability_t hhip_capability_from_name(const char *name)
{
    size_t i;

    if (name == NULL || name[0] == '\0') {
        return (hhip_capability_t)0;
    }
    for (i = 0; i < (sizeof k_hhip_caps / sizeof k_hhip_caps[0]); i++) {
        if (hhip_ascii_ieq(name, k_hhip_caps[i].name) ||
            hhip_ascii_ieq(name, k_hhip_caps[i].wire)) {
            return k_hhip_caps[i].cap;
        }
    }
    return (hhip_capability_t)0;
}
