#include "hhip_lifecycle.h"

/*
 * Explicit from -> to table. Rows are `from`, columns are `to`.
 * 1 = allowed, 0 = rejected.
 *
 *   to:           BOOT DISC CONN CTD  SYNC RUN  UPD  ERR
 * BOOTING          0    1    0    0    0    0    0    1
 * DISCOVERING      0    0    1    0    0    0    0    1
 * CONNECTING       0    1    0    1    0    0    0    1
 * CONNECTED        0    1    0    0    1    1    1    1
 * SYNCING          0    0    0    1    0    1    0    1
 * RUNNING          0    0    1    0    1    0    1    1
 * UPDATING         1    0    0    0    0    1    0    1
 * ERROR            1    1    0    0    0    0    0    0
 */
static const uint8_t k_hhip_lifecycle_table[HHIP_LIFE_COUNT][HHIP_LIFE_COUNT] = {
    /* BOOTING */     {0, 1, 0, 0, 0, 0, 0, 1},
    /* DISCOVERING */ {0, 0, 1, 0, 0, 0, 0, 1},
    /* CONNECTING */  {0, 1, 0, 1, 0, 0, 0, 1},
    /* CONNECTED */   {0, 1, 0, 0, 1, 1, 1, 1},
    /* SYNCING */     {0, 0, 0, 1, 0, 1, 0, 1},
    /* RUNNING */     {0, 0, 1, 0, 1, 0, 1, 1},
    /* UPDATING */    {1, 0, 0, 0, 0, 1, 0, 1},
    /* ERROR */       {1, 1, 0, 0, 0, 0, 0, 0},
};

static const char *const k_hhip_lifecycle_names[HHIP_LIFE_COUNT] = {
    "BOOTING",
    "DISCOVERING",
    "CONNECTING",
    "CONNECTED",
    "SYNCING",
    "RUNNING",
    "UPDATING",
    "ERROR",
};

const char *hhip_lifecycle_name(hhip_lifecycle_state_t state)
{
    if ((int)state < 0 || state >= HHIP_LIFE_COUNT) {
        return "UNKNOWN";
    }
    return k_hhip_lifecycle_names[state];
}

int hhip_lifecycle_is_allowed(hhip_lifecycle_state_t from, hhip_lifecycle_state_t to)
{
    if ((int)from < 0 || from >= HHIP_LIFE_COUNT ||
        (int)to < 0 || to >= HHIP_LIFE_COUNT) {
        return 0;
    }
    return k_hhip_lifecycle_table[from][to] ? 1 : 0;
}

hhip_status_t hhip_lifecycle_transition(hhip_lifecycle_state_t *state,
                                        hhip_lifecycle_state_t next)
{
    if (state == NULL) {
        return HHIP_ERR_NULL;
    }
    if (!hhip_lifecycle_is_allowed(*state, next)) {
        return HHIP_ERR_INVALID_STATE;
    }
    *state = next;
    return HHIP_OK;
}
