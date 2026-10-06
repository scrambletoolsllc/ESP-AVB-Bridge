# Clock rate and raw receive timing investigation, 2026-09-24

The fixed correction in initiator context word 74 is not learned from the
first FTM readings. Audited `ftm_initiator_start_session` calls
`ftm_get_phy_comp` and writes this word before negotiation and measurements.
Negotiated bandwidth changes can select it again. The table is initialized
in SDK `components/esp_wifi/src/ftm_load_calibration.c`, using the C6 constants
in `include/esp_private/ftm_calibration_data.h`. The connected 20 MHz
initiator selection observed here is 704 ticks, or 1.1 microseconds.
`ftm_record_t2t3_cb` adds that correction to raw T3 before converting to ps.
It has remained 704 in all captured good and bad runs.

Each initiator session allocates a fresh context. The inspected upper FTM
path therefore does not support the hypothesis that initial invalid RTTs
train this compensation into a bad value. This does not rule out state or
calibration deeper in the radio hardware or PHY.

## Relative clock rate contributes to negative RTT

`tools/ftm_failure_probe/analyze_rate.py` estimates responder/local rate
separately from T1 versus T2 and T4 versus T3 within each complete report.
It uses integer timestamp differences before floating-point regression,
handles the remote 48-bit wrap, and includes negative RTT entries rather
than selecting only successful measurements. It assumes the propagation
path is stable during the approximately 0.2-second report. Synthetic tests
cover both rate signs, negative RTT, remote wrap, full-width local time,
missing timestamps, ordering and descriptor scaling.

Both directional fits give about -53 ppm. The unscaled subtraction
`(T4-T1)-(T3-T2)` consequently includes about -5.5 ns over the typical
104-microsecond local turnaround. Removing this contribution offline uses
`raw_RTT - rate_delta * (T3-T2)`. This is not a calibrated distance, a
production correction, or proof that every remaining bias is hardware.

| Saved run | Reports | Raw median RTT | Rate-adjusted median RTT |
|---|---:|---:|---:|
| Original diagnostic boot 1 | 24 | -9.375 ns | -3.859 ns |
| Original diagnostic boot 2 | 263 | +4.687 ns | +10.204 ns |
| Original diagnostic boot 3 snapshot | 49 | -4.688 ns | +0.823 ns |
| Reconnect healthy run, all stages | 387 | +1.562 ns | +7.071 ns |
| Reconnect failing run, all stages | 95 | -10.938 ns | -5.436 ns |
| Restored logging snapshot | 445 | -7.813 ns | -2.317 ns |

The relative rate barely changes between the healthy and failing reconnect
runs (-52.839 versus -52.816 ppm). Thus clock-rate mismatch contributes to
negative RTT but cannot account for the approximately 12.5 ns state change.
Artifacts, including the two windows around the earlier long-run transition,
are in `build-ftm-rate/`. Geometry changes around that transition remain
unknown, as documented in the reset investigation.

## Lower receive path and next diagnostic

The audited `libpp.a` code constructs T2 from RX descriptor fields and
obtains T3 from `hal_mac_ftm_get_t3`. In 1.5625 ns ticks:

```
correction = encoded <= 1023 ? encoded : 2048 - encoded
T2_ticks = rx_coarse * 640 - 13312 + rx_phase * 8 + correction
raw_T3_ticks = (tx_coarse * 80 + tx_phase - 640) * 8
T3_ticks = raw_T3_ticks + context_word74
timestamp_ps = ticks * 1562 + floor(ticks / 2)
```

This establishes a 12.5 ns increment for the transmit phase field, not
that this field causes the observed shift. T2 includes a finer correction.
Descriptor byte offsets are RX coarse 12..15, RX phase 11 bits 0..6,
encoded correction 34 bits 4..7 plus 35 bits 0..6, TX coarse 76..79,
and TX phase 80 bits 0..6.

The default-off `CONFIG_FTM_FAILURE_RX_METADATA` wraps the existing T3
getter, calls it first, copies these fields to a bounded ring and returns
the original result unchanged. A short lock protects ring updates and
the report snapshot. The logger matches each entry by its corrected T3;
missing or duplicate matches are explicit. Formatting and reconstruction
checks run outside the receive path. This adds copying and locking to
the diagnostic receive path; it is not a timing-neutral accuracy test.

Additional object hash gates are:

- wdev.o: `1936550cb69bc8c9f9c92e642751aa42532270e94c0e0e082daea9720cbbe81c`
- hal_mac.o: `9a3a51b46fa452656bbdb29306cd496f919ba08df6c8081e9d2ca73a86394537`

The SDK blobs are not modified. Linked disassembly verifies that the
original receive function calls the wrapper and the wrapper calls the
original getter. Build and captures are in `build-ftm-rxmeta/`.
`analyze_rxmeta.py` reconstructs both local timestamps and compares them
exactly with the diagnostic FTM entries, including failed sessions.


## Three boots with raw descriptor capture

All three boots used image SHA256
`f06c744a5b0db7da997f35e3cfb91adf79737d9c1f61db1b0b3437abb5f5a943`,
ELF identity `1fb37c4bd...`. Only the wireless endpoint was restarted;
the bridge and coprocessor were unchanged. Identity was verified before
flashing/resetting and taps were reverified after each restart.

| Boot | Reports / span | Status | Median RTT | Matched descriptors | TX minus RX phase modulo 80 |
|---|---:|---|---:|---:|---:|
| 1 | 39 / 83.546 s | All status 5 | -4.688 ns | 537 | 39 for every match |
| 2 | 124 / 62.993 s | All success | +4.687 ns | 1,713 | 41 for every match |
| 3 snapshot | 42 / 90.196 s | All status 5 | -10.938 ns | 584 | 39 for every match |

Every matched descriptor reconstructs both T2 and T3 exactly. Every entry
with a nonzero T3 has a matching descriptor. Unmatched entries have missing
T3, rather than an observed ring loss. There are no queue drops, panics or
RTT reconstruction disagreements. Partial final reports are explicitly
excluded by the parser. Each log has one boot and the same ELF identity.

The folded RX correction median is 176 ticks in all three boots, with
similar ranges. RX phase values are even and TX phase values odd in all
three. The observed receive-to-ACK phase difference changes by two 80 MHz
steps, or 25 ns, between the failing and successful runs. This is an
association with a lower-level timing state, not proof of which timestamp
is wrong: actual ACK timing can also change. In particular, boots 1 and 3
share phase difference 39 yet differ by 6.25 ns in median RTT. That prevents
this single phase difference from explaining the full problem.

Next, capture responder-side transmit/ACK receive timing as well as the
initiator fields. This can distinguish changes in actual turnaround from
a bias in the responder receive estimate or transmit timestamp mapping.
Changing a constant to force RTT positive would conceal this distinction.
No calibration offset, clock-rate correction or timestamp arithmetic was
changed during these tests. The separate unsigned RTT consumer bug remains
unfixed and is not the driver failure mechanism.

The third boot remains running with metadata logging and no timed reset
sequence. Live log: `build-ftm-rxmeta/boot3.log`; frozen evidence:
`boot3-snapshot.log`, per-boot health/rate/metadata JSON, `comparison.json`
and `provenance.json` in that directory. Four offline regression tests pass;
refactoring the common parser preserves the prior two boot summaries
exactly after JSON normalization. This is not an audio-load or independent
physical clock-synchronization accuracy test.
