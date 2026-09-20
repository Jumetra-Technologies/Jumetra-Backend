#ifndef HHIP_SDK_H
#define HHIP_SDK_H

/*
 * HHIP Embedded SDK — hardware-neutral foundation (Sprint 35).
 *
 * Include this from a board port. Do not include Arduino.h / esp_*.h
 * from SDK headers; keep platform code in the port that fills HAL and
 * transport vtables.
 */

#include "hhip_types.h"
#include "hhip_device.h"
#include "hhip_lifecycle.h"
#include "hhip_capabilities.h"
#include "hhip_protocol.h"
#include "hhip_transport.h"
#include "hhip_hal.h"

#endif /* HHIP_SDK_H */
