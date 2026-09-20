#ifndef HHIP_DEVICE_H
#define HHIP_DEVICE_H

/*
 * Hardware-independent HHIP device abstraction (Sprint 35).
 *
 * Field names match the backend convention used by HardwareNode,
 * PhysicalDevice, and HardwareDevice: board_type (not hardware_type).
 */

#include "hhip_types.h"
#include "hhip_lifecycle.h"
#include "hhip_capabilities.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct hhip_device_config {
    const char *device_id;
    const char *manufacturer;
    const char *model;
    const char *firmware_version;
    const char *board_type;
} hhip_device_config_t;

typedef struct hhip_device {
    char device_id[HHIP_ID_MAX];
    char manufacturer[HHIP_STR_MAX];
    char model[HHIP_STR_MAX];
    char firmware_version[HHIP_STR_MAX];
    char board_type[HHIP_STR_MAX];
    hhip_capability_mask_t capabilities;
    hhip_lifecycle_state_t lifecycle_state;
} hhip_device_t;

/*
 * Initialize a device. Requires non-empty device_id and board_type.
 * Starts in BOOTING with an empty capability set.
 */
hhip_status_t hhip_device_init(hhip_device_t *dev, const hhip_device_config_t *cfg);

hhip_status_t hhip_device_register_capability(hhip_device_t *dev, hhip_capability_t cap);

hhip_status_t hhip_device_set_lifecycle(hhip_device_t *dev, hhip_lifecycle_state_t next);

#ifdef __cplusplus
}
#endif

#endif /* HHIP_DEVICE_H */
