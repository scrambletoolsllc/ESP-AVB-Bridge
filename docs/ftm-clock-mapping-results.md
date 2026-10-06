# FTM clock mapping experiment, 2026-09-22

## Outcome

The first accuracy gate is not met. Application-level ESP-Hosted RPC
exchanges cannot establish a 1 us P4-to-C6 clock mapping with these
measurements. FTM transport works, but an accurate upstream clock anchor
is still missing. Existing beacon discipline remains the operating mode.
The 1 us objective is a proposed engineering target, not a measured result
or a claim about a standards requirement.

The repository now contains an opt-in clock probe and offline analyzer.
The probe does not discipline clocks. Its default configuration is off.

## Measurements

Patched ESP-IDF v6.1, P4 bridge and its onboard C6, wireless C6 endpoint
at the increased distance. Normal FTM offset configuration was retained;
no artificial responder offset was applied. Both chips were identified
before programming; the SDIO updater also checks the onboard C6 MAC.

| Run | Exchanges | Duration | RPC RTT min / median / p99 |
| --- | ---: | ---: | --- |
| Initial idle, no FTM callback | 718 | 151.4 s | 6.527 / 7.265 / 28.927 ms |
| Idle with FTM callback | 330 | 72.3 s | 6.504 / 7.263 / 28.052 ms |
| Wired talker to wireless listener | 276 | 60.9 s | 6.610 / 10.076 / 31.344 ms |

After fitting relative clock rate, the feasible offset interval remains
about 6.4 ms wide at idle and 6.6 ms under load. These intervals are
conditional on the fitted rate; unobserved delay asymmetry prevents an
accuracy claim. Midpoint stability cannot resolve that ambiguity.
The intervals do not mean the actual clock error is necessarily 6 ms.

Under load, the P4 PTP read bracket reaches 199 us and the task-context
C6 MAC read bracket reaches 671 us. Initial idle medians were 2 us for
both reads. AP TSF reads are substantially slower, approximately
194 us median at idle in the callback run and 378 us under load.
Use bracketing and rejection; task-context reads are not automatically
simultaneous even on one chip.

Ethernet taps confirmed approximately 4,000 audio packets/s entering the
bridge from the wired talker. Bridge counters showed forwarding to Wi-Fi.
The listener reported sequence gaps, including cumulative seq_gap=3637
near the end. This was a timing-load experiment, not an audio-quality pass.
The test stream was disconnected successfully afterwards.

## Timestamp domains

The linked `esp_wifi_internal_get_mac_clock_time()` reads a 32-bit
microsecond register at 0x600ad000 on this C6. Its documented sleep
restriction applies. It wraps after approximately 71.6 minutes.
The diagnostic callback reads the same register directly, because the
public getter is flash-resident and Wi-Fi APIs are forbidden there.
Disassembly confirmed the callback and its direct callees are in IRAM.
This is a build-specific diagnostic, not a supported production interface.

The callback receives the previous exchange's full-width T1/T4 in
picoseconds. At callback entry, MAC time is generally about 1.9 ms after
that previous ACK at idle, consistent with the interframe schedule.
The shortest observed gap is approximately 73 us. This supports a common
MAC/FTM epoch but does not establish a submicrosecond conversion offset.
The callback is not coincident with the previous ACK.

AP TSF has a different epoch: in the callback run it is approximately
211 ms behind the MAC clock. Projecting a nearby TSF sample to callback
entry places TSF roughly 209 ms *before* the previous FTM ACK timestamp,
although the callback occurs afterwards. Therefore FTM timestamps cannot
be treated as AP TSF without an explicit conversion. The comment in
`esp_ptp/ptp_wifi.c` making that assumption needs correction with the
production mapping work. These measurements cover the responder only;
the initiator-to-endpoint-local mapping still needs its own experiment.

The captured initiator report's lower-48-bit picosecond wrap is a separate
281.475 s wrap. Neither that wrap nor the 32-bit MAC wrap was crossed in
these short hardware runs. The analyzer has a synthetic MAC-wrap test.

## Next implementation decision

Do not feed RPC midpoint timestamps into the endpoint servo as accurate
FTM anchors. First prototype a shared hardware timing edge:

1. P4 Ethernet driver exposes `esp_eth_mac_set_pps_out_gpio()` and
   `esp_eth_mac_set_pps_out_freq()`, allowing a hardware PTP-derived pulse.
2. C6 has GPIO ETM events and GPTimer capture tasks. Capture the edge in
   hardware and retrieve the latched value later, outside an ISR.
3. Establish the captured timer's relationship to the FTM/MAC counter,
   including resolution, reset generation, frequency ratio and uncertainty.
4. Verify the result with independent capture equipment before proceeding
   to timing snapshots, per-frame IEs and endpoint servo injection.

This requires a confirmed spare P4 output, accessible C6 input and a
physical connection between them. No new connection was assumed or
configured. Avoid the reset signal, active SDIO pins and boot-strapping
pins unless their use is explicitly designed and verified. The C6 H7
header has no EN pin; the Prog2 does not supply the missing timing edge.
PPS/capture support alone is not proof the complete mapping will meet 1 us.

An alternative is driver support for a documented coincident cross-domain
capture or deterministic transport timestamping with a measured error
bound. Merely increasing RPC rate or averaging does not remove unknown
path asymmetry.

## Questions prepared for Espressif, not sent

- Confirm the exact counter/epoch and units behind responder callback
  T1/T4 and initiator T2/T3, including their relation to the MAC timer and
  AP/STA TSF. Observations show AP TSF has a different epoch.
- Is a supported IRAM-safe read of the full-resolution FTM counter
  available, or a coherent capture paired with a CPU/peripheral timer?
- Can an external GPIO edge latch that counter, or can the counter be
  paired with an ETM-capable timer with a documented error bound?
- Confirm reset/sleep behavior, full-width callback wrap and the report's
  lower-48-bit truncation contract.

## Artifacts and validation

`components/ftm_clock_probe/` contains the shared diagnostic component;
`coprocessor/components/ftm_clock_probe` links to it. The analyzer and
usage notes are under `tools/ftm_clock_probe/`.

Ignored local `build-ftm-clock/` contains configs, builds, serial logs,
JSON analyses, tap captures, flash/restore logs and tested-image hashes.
Exact tested second-probe images are in `tested-images/`; the final source
also adds a defensive IE-buffer-length check. Both enabled target builds
pass. Analyzer tests cover drift, asymmetric delay, MAC wrap, malformed
records, duplicates, boot separation and PTP steps versus slow reads.

No commits or pushes were made. No switch power cycle was needed.

Restoration completed: normal patched coprocessor and bridge images, plus
the original P4 staging partition, were written and verified. The endpoint
firmware was not changed. Both endpoints rediscovered the same BTC,
00:01:f2:ff:fe:ff:3b:14. A post-restoration checkpoint recorded 82 successful
FTM sessions, zero failures and median raw RTT 43.770 ns. This verifies
ranging recovery, not clock accuracy. Serial monitors were closed and
ports released. The disabled-probe host build also passes, and its ELF
contains no probe symbols. Five analyzer tests pass.

Follow-up: [shared-edge experiment](ftm-shared-edge-results.md) resolves
the physical P4/C6 transfer path using the existing GPIO6/R52/GPIO2 trace.
The RPC-midpoint limitation above remains valid.
