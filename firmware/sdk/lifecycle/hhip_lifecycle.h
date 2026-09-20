#ifndef HHIP_LIFECYCLE_H
#define HHIP_LIFECYCLE_H

/*
 * Firmware-side device lifecycle (Sprint 35).
 *
 * Firmware lifecycle vs backend HardwareNodeStatus
 * ------------------------------------------------
 * This machine is intentionally richer than
 * engine.hardware_nodes.hardware_node.HardwareNodeStatus
 * (CONNECTING / ONLINE / WAITING / OFFLINE / ERROR). Firmware states such
 * as BOOTING, DISCOVERING, SYNCING, UPDATING, and RUNNING are not mapped
 * here. Which outbound message accompanies a firmware transition, and which
 * inbound message updates HardwareNodeStatus, is a transport-layer decision
 * deferred to the sprint that implements a real transport. Do not default
 * that mapping without an explicit decision — it is deliberately unmapped.
 */

#include "hhip_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum hhip_lifecycle_state {
    HHIP_LIFE_BOOTING = 0,
    HHIP_LIFE_DISCOVERING,
    HHIP_LIFE_CONNECTING,
    HHIP_LIFE_CONNECTED,
    HHIP_LIFE_SYNCING,
    HHIP_LIFE_RUNNING,
    HHIP_LIFE_UPDATING,
    HHIP_LIFE_ERROR,
    HHIP_LIFE_COUNT
} hhip_lifecycle_state_t;

const char *hhip_lifecycle_name(hhip_lifecycle_state_t state);

/* 1 if (from -> to) is in the explicit transition table, else 0. */
int hhip_lifecycle_is_allowed(hhip_lifecycle_state_t from, hhip_lifecycle_state_t to);

/*
 * Apply a transition in place. Returns HHIP_OK on success.
 * Invalid pairs (and unknown states) return HHIP_ERR_INVALID_STATE and
 * leave *state unchanged — they are rejected, never silently applied.
 */
hhip_status_t hhip_lifecycle_transition(hhip_lifecycle_state_t *state,
                                        hhip_lifecycle_state_t next);

#ifdef __cplusplus
}
#endif

#endif /* HHIP_LIFECYCLE_H */
