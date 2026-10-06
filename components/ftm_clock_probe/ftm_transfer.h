#pragma once
#include <stdint.h>

/* Share the request channel, the hosted callback table has three slots. */
#define PROBE_TRANSFER_ID 0x434c4b01U
#define PROBE_TRANSFER_VERSION 1U

/* Private little-endian RPC, explicitly sized on P4 and C6. */
typedef struct {
    int64_t reference_ns, rate_q32, upstream_receive_ns;
    uint64_t radio_edge;
    uint32_t version, host_boot, radio_boot, generation;
    uint32_t edge_sequence, publication, mac_us, valid;
    int32_t peer_delay_ns;
    uint8_t follow_up[76], source_port[10], btc_identity[8], padding[6];
} ftm_transfer_t;

_Static_assert(sizeof(ftm_transfer_t) == 168, "FTM transfer layout");
