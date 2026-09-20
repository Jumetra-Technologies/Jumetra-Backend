#include "hhip_device.h"

hhip_status_t hhip_device_init(hhip_device_t *dev, const hhip_device_config_t *cfg)
{
    hhip_status_t rc;

    if (dev == NULL || cfg == NULL) {
        return HHIP_ERR_NULL;
    }
    if (cfg->device_id == NULL || cfg->device_id[0] == '\0' ||
        cfg->board_type == NULL || cfg->board_type[0] == '\0') {
        return HHIP_ERR_INVALID_MESSAGE;
    }

    memset(dev, 0, sizeof(*dev));

    rc = hhip_str_copy(dev->device_id, sizeof(dev->device_id), cfg->device_id);
    if (rc != HHIP_OK) {
        return rc;
    }
    rc = hhip_str_copy(dev->manufacturer, sizeof(dev->manufacturer),
                       cfg->manufacturer != NULL ? cfg->manufacturer : "");
    if (rc != HHIP_OK) {
        return rc;
    }
    rc = hhip_str_copy(dev->model, sizeof(dev->model),
                       cfg->model != NULL ? cfg->model : "");
    if (rc != HHIP_OK) {
        return rc;
    }
    rc = hhip_str_copy(dev->firmware_version, sizeof(dev->firmware_version),
                       cfg->firmware_version != NULL ? cfg->firmware_version : "");
    if (rc != HHIP_OK) {
        return rc;
    }
    rc = hhip_str_copy(dev->board_type, sizeof(dev->board_type), cfg->board_type);
    if (rc != HHIP_OK) {
        return rc;
    }

    dev->capabilities = 0;
    dev->lifecycle_state = HHIP_LIFE_BOOTING;
    return HHIP_OK;
}

hhip_status_t hhip_device_register_capability(hhip_device_t *dev, hhip_capability_t cap)
{
    if (dev == NULL) {
        return HHIP_ERR_NULL;
    }
    return hhip_capabilities_register(&dev->capabilities, cap);
}

hhip_status_t hhip_device_set_lifecycle(hhip_device_t *dev, hhip_lifecycle_state_t next)
{
    if (dev == NULL) {
        return HHIP_ERR_NULL;
    }
    return hhip_lifecycle_transition(&dev->lifecycle_state, next);
}
