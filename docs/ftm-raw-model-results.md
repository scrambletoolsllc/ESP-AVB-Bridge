# Raw FTM clock model and rollover test, 2026-09-24

A default-off recorder and offline relative clock model now run against
actual C6 FTM reports. Coarse/fine timestamp reconstruction helpers have
boundary tests. The model has not been installed as a firmware clock
source or servo. Beacon discipline remains active.

## Recorder and model

The recorder wraps the existing FTM initiation/report APIs. It copies at
most 16 entries into a bounded queue, with a static staging buffer and a
nonblocking busy guard. A separate task formats the records. This avoids
adding a report-sized allocation to the 2304-byte event-task stack.
Association generation, peer, attempt number and dropped-report count are
recorded. No SDK/blob changes were made during this test.

The offline model extends responder T1/T4 modulo 2^48 picoseconds while
retaining full-width initiator T2/T3. It uses hardware timestamp midpoints,
integer epoch anchors and a 32-report moving relative-rate fit. Every
report is predicted before it is added to the fit. Local callback MAC
reads check freshness only; observed callback delay reached 215 ms.
Full remote boot epoch is still arbitrary until a responder coarse anchor
and boot identity are carried across the link.

The tested fine_mac_ticks helper combines a fresh coarse MAC read with a
calibrated MCPWM phase interval, including timer-cycle boundary selection.
It is not yet connected to a live firmware high-resolution time source.
See tools/ftm_raw_probe/README.md for assumptions, gates and reproduction.

## Rollover defect reproduced and fixed

The existing esp_ptp ranging handler compared raw FTM T1 values as if they
were a monotonic AP TSF. At the normal wrap, the last valid T1 changed from
281317135057221 to 349504946565 ps. The modular forward interval was
507346600000 ps, about 0.507 seconds, not a clock reset.

The handler nevertheless rejected it as a backward sample and returned
without setting the report-completion event. Ranging slowed from about
0.51 to 2.2 seconds. The offline model then correctly expired its two-second
continuity gate. The saved pre-fix snapshot contains 558 reports, 33 model
rejects and 34 model segments over 403.37 seconds. This is retained as
failure evidence, not removed from the record.

The uncommitted esp_ptp change:

- compares FTM continuity modulo its 48-bit period;
- compares fresh beacon TSF against its own previous beacon value, never
  against the FTM counter, when checking reboot evidence;
- takes the beacon value and receive-time snapshot under a short lock;
- clears continuity history on association changes;
- signals completion of consumed successful reports on rejection paths.

The old candidate patch that extended FTM epochs from beacon TSF was not
used: these are different counters. Native UBSan tests include the exact
recorded wrap and backward/ambiguous boundary cases. Actual responder
reboot recovery, very long ranging outages, and the 71.6-minute MAC wrap
remain unvalidated on hardware. This is not a full recovery certification.

## Fixed live run

| Metric | Result |
|---|---:|
| Complete reports | 713 |
| Duration | 364.556326 s |
| Timestamp entries | 9,895 |
| Invalid RTT entries excluded | 63 |
| Recorder drops / model rejects | 0 / 0 |
| Model segments | 1 |
| Responder 48-bit wraps | 1 |
| Initiator crossings of the 48-bit boundary | 1, full width retained |
| Predicted reports / entries | 705 / 9,720 |
| Absolute prediction error, median | 24.79 ns |
| Absolute prediction error, P99 | 82.93 ns |
| Absolute prediction error, maximum | 94.42 ns |
| Remote-relative rate, median | -52.921 ppm |

These are causal timestamp-model prediction errors, not measured GPIO
alignment or absolute synchronization accuracy. Fixed counter bias, path
asymmetry, calibration intervals and hardware output scheduling are not
included. The recorder log snapshot excludes its one unfinished final
report explicitly; complete reports were not pruned. No FTM failure,
backward-counter warning or panic was logged in the fixed capture.

Twenty-four Python tests pass, along with native counter regression tests,
the prior eleven MAC-calibration analyzer tests, and C6/P4 builds. The
normal endpoint ELF has neither raw-recorder wrappers nor MAC-calibration
sampler symbols.

## Scope and audio status

The Rigol was reachable and five paired RAW WORD captures showed both
existing beacon-based outputs. CH2 minus CH1 was 5.704..5.736 ms, median
5.728 ms, with an 8 us sampling interval. This is a coarse baseline from
the existing discipline, not a test of the new FTM model. The scope is
left running at 5 ms/div with both probes set to 10X.

The user reported moving a host connection during an earlier interruption;
that interruption must not be assigned a firmware cause without a clean
retest. A new wired-to-wireless audio request returned ACMP success but
bandwidth admission failed, and the listener received zero packets. It
was disconnected and the talker connection count verified zero. Thus this
fixed run is not an audio-load validation, and the earlier audio delivery
issue remains unresolved rather than attributed to a confirmed cause.

## Images, changes and next work

The final diagnostic image hash is
73db065221a44c27416c0706671509f3055e5ae21e39e1d9406e92252c9a0937.
The restored normal endpoint image retains the rollover fix and scope
output, with both recorder and MAC-calibration diagnostics disabled:
9e19e9173b84b3d86ae9a3a00112425d836fbe45217bae2b8037c3eb0681a985.
Bridge P4 and onboard responder firmware were unchanged in this run.

Artifacts are under ignored build-ftm-raw/: original/fixed serial logs,
complete-report snapshots and analyses, failure/wrap evidence, image
manifests, build/flash/restore logs, scope waveforms, tap verification,
audio connection logs and ptp-wrap-fix.patch. The shared esp_ptp repo has
uncommitted ptp_wifi.c changes and a new ptp_ftm_counter.h; no commits or
pushes were made. Apply the component version convention when committing.

Next: implement the bounded firmware model and live high-resolution MAC
time source; carry genuine responder boot/coarse anchors and P4/upstream
mapping/source validity; then drive and compare independent hardware
outputs before enabling FTM discipline. The successful offline fit is a
prerequisite for that integration, not its completion.

Post-restoration check: normal image boots and emits scope pulses, with
recorder disabled and no panic. However its radio reports status5 invalid
RTT measurements after this reboot. This is separate from the saved fixed
recorder run, which had no FTM failure logs; do not describe current normal
ranging as healthy or attribute the change to geometry/firmware without
a controlled follow-up. Counts are in build-ftm-raw/restoration-health.json.
Endpoint holder session90099 PID426610 remains active on ACM0.

## Normal firmware restart comparison, 2026-09-24 07:50 UTC

After 103 failed sessions and zero successes on the restored normal image,
restarted only the wireless endpoint using esptool read-mac, verifying the
same fc:01:2c:fd:fe:80 identity. No flash, configuration, responder, or scope
change. Both boots report the same ELF identity ae376b2c0... . The next
saved observation contains 80 successful sessions, zero failures, and
3.124..7.812 ns RTT. Thus the recorder is not required for successful
ranging; the failure was not persistent across boots of the same image.
Boot-dependent radio/timestamp state near the measurement floor is a
hypothesis, not a demonstrated internal cause. Zero aggregate RTT in the
failed sessions does not reveal the rejected raw timestamp values.
Evidence: build-ftm-raw/normal-restart-comparison.json and the two normal
serial logs. Previous restoration failure remains preserved; this restart
supersedes its current-health status. Endpoint monitor session88234,
PID427332, ACM0 -> build-ftm-raw/endpoint-normal-restart.log. Previous90099
holder stopped. Bridge holders remain unchanged. No new source changes.
