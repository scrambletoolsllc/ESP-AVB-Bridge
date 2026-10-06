# Internal FTM failure recorder

This diagnostic component captures measurements that the public FTM API
cannot return after `FTM_STATUS_NO_VALID_MSMT`. It is default off and tied
to the exact supplied ESP32-C6 blob, not a portable production interface.

## Capture and ownership

`components/ftm_failure_probe/CMakeLists.txt` extracts `ieee80211_ftm.o`
from the SDK archive into the build directory and requires SHA256
`79607f4b192e89b4e2380ec2a332c6d64907af49dfbb8d63f8f7ac901fee4500`.
It adds three data-symbol aliases with objcopy and links that object in the
probe component. The SDK files are not modified. All 91 allocated code/data
sections were compared byte-for-byte with the input object and matched.
The map confirms the diagnostic object supplies the FTM implementation.
No binary or blob source belongs in this repository.

The audited private layout is:

| Object | Offset | Meaning used by the probe |
|---|---:|---|
| s_ftm_initiator | 48 | allocated entry count, uint32 |
| s_ftm_initiator | 72, 74 | bandwidth flag at byte 72 (logged as uint16), PHY compensation ticks at word 74 |
| s_ftm_initiator | 76 | received count, cleared on successful event construction |
| s_ftm_initiator | 80 | report pointer |
| g_ftm_report_data | 0 | report pointer after ownership transfer |
| g_ftm_report_num_entries | 0 | transferred report count, uint8 |

Disassembly of `ftm_parse_data` shows that failed reports are transferred
into the global report, logged, then freed before `wifi_event_post` runs.
Therefore an event-only probe cannot capture them. The diagnostic wraps
`esp_wifi_init`, copies its OS adapter table, and replaces only `_free`.
The release hook recognizes the current global FTM report and copies up
to 16 entries into static storage before forwarding the original free.
It requires an active context whose report has already transferred, which
excludes the previous report's cleanup at the start of classification.
No allocation, formatting or queue operation is added to this hook.

The event-post wrapper snapshots the matching saved failure or the live
successful report, then makes a nonblocking copy into a four-record queue.
A separate priority-2 task formats the records. Successful report ownership
and the application's getter remain unchanged. Hardware timestamp callbacks,
RTT arithmetic, calibration values and ranging parameters are not patched.
The probe does add an allocator dispatch check and report-copy/logging load;
this is diagnostic firmware, not a timing-neutral accuracy measurement.

An additional default-off `CONFIG_FTM_FAILURE_RX_METADATA` option wraps
the low-level T3 getter and copies RX descriptor timing fields after its
original read. This option adds bounded copying and locking in the receive
path. It also requires the exact audited wdev.o and hal_mac.o hashes.
See `docs/ftm-rate-and-rx-investigation.md` for the reconstruction formulas,
assumptions and build provenance. SDK blob files remain unchanged.

`FTMRXMETA` fields are report sequence, entry index, descriptor sequence,
raw T3 ticks, RX coarse count, RX phase, encoded RX correction, TX coarse
count and TX phase. The worker matches by corrected T3; absent or ambiguous
matches emit `FTMRXMETA_MISSING` instead. `analyze_rxmeta.py` verifies both
local timestamp reconstructions and counts missing nonzero T3 matches.

`analyze_rate.py` independently estimates relative timestamp clock rate
within each report using both directions, including negative RTT entries.
Its rate-adjusted RTT is an offline diagnostic, not a firmware correction
or calibrated distance. Use `--first` / `--last` to select report sequences.

The default-off `CONFIG_FTM_RESPONDER_PROBE` component can be enabled on
the bridge C6 for paired capture. `FTMRESP` fields are sequence, local time
us, peer MAC, dialog token, raw T1 ticks, raw T4 ticks, converted T1 ps,
converted T4 ps, compensation ticks, RSSI, context-found flag and queue
drops. `FTMRESP_BEGIN,1` identifies each responder boot.
`analyze_paired.py` matches exact remote timestamp pairs and verifies the
token and conversion. `--allow-responder-reboots` explicitly separates
multiple boots; `--require-matches` rejects missing or ambiguous pairs,
conversion disagreements and queue loss. See
`docs/ftm-paired-capture-results.md` for the hardware comparison and limits.

## Configuration and records

Enable `CONFIG_FTM_FAILURE_PROBE` in an isolated C6 endpoint build, using
its normal codec pins. Keep `FTM_RAW_PROBE`, `FTM_LIVE_MODEL`,
`FTM_LIVE_MODEL_SELF_TEST`, and `MAC_TRANSITION_PROBE` disabled. Existing
scope output can remain enabled. The current build uses the isolated
`build-scope/endpoint` project and `build-ftm-debug/sdkconfig.endpoint`.

`FTMDEBUG_BEGIN,1` marks one boot. `FTMDEBUG` fields are:

sequence, event time us, status, public entry count, allocated count,
received count, capture source, copied count, context word72, word74,
aggregate raw RTT ns, estimated RTT ns, cumulative queue drops.

Capture sources: 1 active context, 2 global successful report,
3 saved report from the release hook. `FTMREJECT` is the entry record name
for both successful and failed reports; its fields are sequence, index,
dialog token, RSSI, uint32 RTT field, T1, T2, T3, T4 in ps, and ppm.

```sh
python3 tools/ftm_failure_probe/analyze.py build-ftm-debug/boot1.log
```

The analyzer recomputes `(T4-T1)-(T3-T2)` using integer arithmetic and
compares the result with the driver's uint32 field. Based on the audited
classification code, differences outside -25,000..10,000,000 ps receive
UINT32_MAX; in-range negative values retain their two's-complement bits.
Only strictly positive differences contribute to the driver's average.
Missing or backward timestamps are classified separately. These tests
include no timestamp wrap inside a single turnaround; the analyzer labels
backward stamps rather than silently extending them. A partial trailing
report is explicitly counted and omitted; incomplete intervening reports
are errors. Analyze one boot per log.

The private layout and call ordering must be re-audited if the blob changes.
A hash mismatch fails the build. Do not bypass it by changing the expected
hash alone. The hardware samples and provenance are documented in
`docs/ftm-failure-investigation.md`.

## Timed reset experiment

`CONFIG_FTM_FAILURE_RESET_TEST` is default off and requires the failure
probe. It logs a baseline, requests association-only disconnect at 60 s,
then Wi-Fi stop/start at 120 s, and completion at 180 s after its first
report. The existing application reconnects on disconnect/start events.
Each action is logged with its return code. These actions repeat after a
boot of this diagnostic image; restore the logging-only image afterward.

```sh
python3 tools/ftm_failure_probe/analyze_reset.py \
  build-ftm-reconnect/run1.log --require-complete
```

The analyzer separates reports by explicit action markers and checks
completion, API returns, queue drops and panics. A healthy baseline is a
control, not evidence that a reset cures the all-invalid condition.
