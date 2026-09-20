#ifndef HHIP_CAPABILITIES_H
#define HHIP_CAPABILITIES_H

/*
 * Device capability registry (Sprint 35).
 *
 * Canonical names match the prompt list (GPIO, ADC, ...). Wire aliases
 * are lowercase to match backend CapabilityKind / sketch advertisements
 * (gpio, adc, ...).
 *
 * CAN, MODBUS, and ETHERNET are intentionally forward-looking for
 * industrial gateways. The current backend interfaces vocabulary only
 * recognizes gpio/adc/pwm/uart/spi/i2c — advertising the extra three
 * will not connect to anything on the host yet. That is expected; do
 * not add backend handling here.
 */

#include "hhip_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum hhip_capability {
    HHIP_CAP_GPIO     = 1u << 0,
    HHIP_CAP_ADC      = 1u << 1,
    HHIP_CAP_PWM      = 1u << 2,
    HHIP_CAP_SPI      = 1u << 3,
    HHIP_CAP_I2C      = 1u << 4,
    HHIP_CAP_UART     = 1u << 5,
    HHIP_CAP_CAN      = 1u << 6,
    HHIP_CAP_MODBUS   = 1u << 7,
    HHIP_CAP_ETHERNET = 1u << 8
} hhip_capability_t;

typedef uint32_t hhip_capability_mask_t;

#define HHIP_CAP_KNOWN_MASK \
    (HHIP_CAP_GPIO | HHIP_CAP_ADC | HHIP_CAP_PWM | HHIP_CAP_SPI | HHIP_CAP_I2C | \
     HHIP_CAP_UART | HHIP_CAP_CAN | HHIP_CAP_MODBUS | HHIP_CAP_ETHERNET)

hhip_status_t hhip_capabilities_register(hhip_capability_mask_t *set,
                                         hhip_capability_t cap);

/* Accepts "GPIO" / "gpio" (and the rest of the registry). */
hhip_status_t hhip_capabilities_register_name(hhip_capability_mask_t *set,
                                              const char *name);

int hhip_capabilities_has(hhip_capability_mask_t set, hhip_capability_t cap);

/* SDK canonical name, e.g. "GPIO". */
const char *hhip_capability_name(hhip_capability_t cap);

/* Backend/sketch alias, e.g. "gpio". */
const char *hhip_capability_wire_name(hhip_capability_t cap);

hhip_capability_t hhip_capability_from_name(const char *name);

#ifdef __cplusplus
}
#endif

#endif /* HHIP_CAPABILITIES_H */
