#ifndef HHIP_HAL_H
#define HHIP_HAL_H

/*
 * Hardware Abstraction Layer — interfaces only (Sprint 35).
 *
 * No board-specific GPIO/PWM/ADC code lives here. A platform port
 * (ESP32, STM32, Arduino, RP2040, nRF52, industrial gateway) fills
 * in these function pointers. The SDK never calls Arduino or ESP-IDF
 * APIs itself.
 */

#include "hhip_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct hhip_hal {
    void *ctx;
    int (*gpio_write)(void *ctx, int pin, int value);
    int (*gpio_read)(void *ctx, int pin, int *out_value);
    int (*pwm_write)(void *ctx, int pin, unsigned duty, unsigned freq_hz);
    int (*analog_read)(void *ctx, int pin, int *out_value);
} hhip_hal_t;

static inline hhip_status_t hhip_hal_gpio_write(hhip_hal_t *hal, int pin, int value)
{
    if (hal == NULL || hal->gpio_write == NULL) {
        return HHIP_ERR_NO_HAL;
    }
    return hal->gpio_write(hal->ctx, pin, value) == 0 ? HHIP_OK : HHIP_ERR_INTERNAL_ERROR;
}

static inline hhip_status_t hhip_hal_gpio_read(hhip_hal_t *hal, int pin, int *out_value)
{
    if (hal == NULL || hal->gpio_read == NULL || out_value == NULL) {
        return (out_value == NULL) ? HHIP_ERR_NULL : HHIP_ERR_NO_HAL;
    }
    return hal->gpio_read(hal->ctx, pin, out_value) == 0 ? HHIP_OK : HHIP_ERR_INTERNAL_ERROR;
}

static inline hhip_status_t hhip_hal_pwm_write(hhip_hal_t *hal, int pin,
                                               unsigned duty, unsigned freq_hz)
{
    if (hal == NULL || hal->pwm_write == NULL) {
        return HHIP_ERR_NO_HAL;
    }
    return hal->pwm_write(hal->ctx, pin, duty, freq_hz) == 0 ? HHIP_OK
                                                             : HHIP_ERR_INTERNAL_ERROR;
}

static inline hhip_status_t hhip_hal_analog_read(hhip_hal_t *hal, int pin, int *out_value)
{
    if (hal == NULL || hal->analog_read == NULL || out_value == NULL) {
        return (out_value == NULL) ? HHIP_ERR_NULL : HHIP_ERR_NO_HAL;
    }
    return hal->analog_read(hal->ctx, pin, out_value) == 0 ? HHIP_OK
                                                           : HHIP_ERR_INTERNAL_ERROR;
}

#ifdef __cplusplus
}
#endif

#endif /* HHIP_HAL_H */
