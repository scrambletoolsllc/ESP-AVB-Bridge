# Raw FTM clock-model experiment

This is a default-off recorder and an offline relative-clock prototype.
It does not change the beacon servo, audio clock, FTM parameters, or GPIO
output timing. Enable CONFIG_FTM_RAW_PROBE in an isolated C6 endpoint
build. Keep the endpoint's actual codec pins and scope configuration.

The component wraps the existing esp_wifi_ftm_initiate_session and
esp_wifi_ftm_get_report calls at link time. The application still consumes
each report once. A fixed buffer and four-element queue copy at most 16
entries without waiting. A separate task formats and logs the data.
The original event task has a 2304-byte stack; the extra report buffer
therefore lives in static storage, with a nonblocking busy guard.
No shared SDK or PTP source is edited. The normal application has one
initiator session at a time; concurrent session initiators are outside
this diagnostic's supported configuration.

Association changes increment a generation. Each initiation has an
attempt number and peer address. Headers contain a bracketed local MAC
read and cumulative recorder-drop count; entries contain dialog token,
RSSI, RTT, T1..T4 and the driver's ppm field. The generation is an observed
association generation, not a proven responder boot identifier.

## Timestamp reconstruction

Responder T1/T4 are 48-bit picoseconds, period 281.474976710656 seconds.
Initiator T2/T3 retain their full SDK width. An initially arbitrary remote
epoch is extended using successive hardware observations; gaps over two
seconds, backward timestamps, implausible turnarounds or ambiguous
extensions are rejected. Peer/association changes discard the old model.
A rejected report is counted and forces reacquisition in the analyzer.

The local 32-bit microsecond MAC read is extended near hardware T3, modulo
2^32 microseconds. This verifies report freshness, not phase: the callback
may arrive milliseconds after the radio event. Read brackets must be at
most 50 us, and report age at most 500 ms. Full epochs remain integers.

model.py also provides fine_mac_ticks: combine a fresh coarse MAC read,
MCPWM phase and the calibrated phase interval into a full 40 MHz interval.
It covers the 1.5 ms timer wrap and the upper range of the 32-bit MAC.
It assumes a common timer generation and bounded coarse/fine read spacing;
the caller must enforce those conditions. This helper is tested with
synthetic boundaries but is not yet wired into a live hardware clock.

Absolute responder boot epoch still needs a fresh responder coarse anchor
and explicit boot identity. The prototype cannot establish those from
truncated FTM timestamps alone. Do not feed its arbitrary intercept into
the upstream AVB clock or treat AP TSF as that anchor.

## Relative rate and phase

For each valid entry, form remote (T1+T4)/2 and local (T2+T3)/2 after
extending T4 relative to T1. Their relationship assumes symmetric path
delay; fixed timestamp bias and asymmetry remain uncalibrated.

Use one integer median phase observation per report and fit a moving
32-report linear model, starting after eight reports. Fit small correction
and elapsed-time differences around integer anchors, not full-epoch
floating-point timestamps. Rates outside +/-200 ppm and median innovations
over 20 us are rejected. These are experimental plausibility gates, not
an accuracy specification. Evaluate every new report against the previous
model before inserting it, so reported errors are causal predictions.
Model fit/residuals cannot certify physical synchronization accuracy.

Analyze one recorder boot with:

```
python3 tools/ftm_raw_probe/analyze.py capture.log
python3 -m unittest discover -s tools/ftm_raw_probe -p 'test_*.py'
```

The parser rejects mixed boots, missing entries, duplicate/reordered
reports, malformed fields and truncated final reports. If taking a snapshot
of a live log, explicitly exclude only its unfinished last report and
record that exclusion. Drop counters and all rejected reports remain in
the result. Do not remove inconvenient complete reports.

## Next integration boundaries

The offline model must become a bounded task-level firmware model with
immutable validity-tagged snapshots before it can drive outputs. Add
actual responder boot/coarse anchors, implement and validate a live fine
MAC time source, and carry P4/shared-edge/upstream-source mappings through
the vendor IE. Then independently compare hardware outputs before enabling
FTM clock/audio discipline. Existing beacon scope measurements remain a
baseline only. Audio forwarding losses are a separate unresolved issue.

## Rollover regression in the existing ranging handler

The first live capture reproduced a separate bug in esp_ptp/ptp_wifi.c:
raw T1 dropped at the ordinary 48-bit wrap, the handler called it a bad
backward sample, and its early exit omitted the report-completion bit.
Successful ranging then ran at about 2.2 seconds rather than 0.51 seconds,
expiring this experiment's two-second model age gate.

The accompanying esp_ptp change uses ptp_ftm_counter.h for modular
continuity, compares beacon TSF against its own previous value for reboot
evidence, resets continuity on association changes, and completes consumed
reports on rejection paths too. A protected, freshness-checked beacon
snapshot avoids comparing a torn or expired TSF value. It does not use
beacon TSF to reconstruct an FTM epoch. Native regression checks:

```
cc -Wall -Wextra -Werror -fsanitize=undefined \
  -I /home/dev/Development/esp_ptp tools/ftm_raw_probe/test_counter.c \
  -o /tmp/test_ftm_counter
/tmp/test_ftm_counter
```

Actual responder reboot recovery and long MAC rollovers still require
hardware testing. A normal 48-bit wrap test does not substitute for them.
