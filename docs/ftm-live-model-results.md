# Live relative FTM model, 2026-09-24

The portable C model now runs in the endpoint recorder worker in an
isolated diagnostic build. It publishes an observation-only offset/rate
snapshot. Existing beacon discipline, scope output scheduling and audio
control do not consume it. Bridge firmware was unchanged for this test.

The implementation and reproduction commands are documented in
`tools/ftm_clock_model/README.md`. It uses integer epoch anchors, full-width
initiator timestamps, modular responder timestamps, a bounded 32-report
fit and prediction before insertion. Model publication requires eight
reports and expires after two seconds. Association changes, capture drops,
bad ordering and rejected measurements invalidate prior state.

## Numerical and rejection checks

Native UBSan tests pass for remote 48-bit rollover, coarse MAC 32-bit
rollover, stale/generation/peer/drop reset, invalid input and queue age,
duplicate attempts, local/remote steps, excessive rate and innovation,
and eight-report reacquisition. The coarse MAC rollover is synthetic;
this run does not establish physical recovery at 71.6 minutes uptime.

The C implementation matches the Python reference across the prior 713
recorded reports, with maximum prediction difference below 0.000001 ps.
This checks numerical equivalence, not physical clock accuracy. The live
analyzer separately compares firmware status, validity, entry/wrap counts
and predictions with native replay, then checks accepted predictions with
Python. It fails on missing rows or divergent decisions. Intentional
input skips and a partial trailing report are explicitly counted.

## Hardware run

The diagnostic image is SHA256
e4d31bf1cb55e61cfe9c32db1fad4ff6dec0dc81ade25fcc5e079e4d1723fa23,
ELF identity 5723c9f32... . Endpoint identity and codec pins were preserved.
The first boot produced ten failed FTM sessions and no raw reports; the
first controlled restart produced 35 failures and no raw reports. The
second restart of the identical image produced usable reports. These
logs are retained in `build-ftm-live/boot-comparison.json` and the three
endpoint logs. No geometry or calibration change was made between boots.
The internal cause of this boot-dependent behavior is not established.

The self-test pauses model input for four seconds while ranging continues,
then requests a Wi-Fi disconnect after six minutes. It must be disabled
or the normal image restored when testing finishes, because it repeats
after every boot. The raw log retains every complete report, including
the eight intentionally skipped model inputs and stale rejection.

The model computes and formats logs outside the Wi-Fi report callback.
Reported compute duration is wall time, including preemption. It is not
a worst-case execution-time guarantee or an audio-load validation.

The completed run is `build-ftm-live/live-final.log`; the strict comparison
result is `live-final-analysis.json` in the same directory:

| Metric | Result |
|---|---:|
| Complete reports / elapsed time | 885 / 452.732111 s |
| Evaluated / intentionally skipped | 877 / 8 |
| Accepted / expected stale rejections | 875 / 2 |
| Recorder drops / unexpected rejections | 0 / 0 |
| Responder 48-bit wraps | 2 |
| Firmware versus native prediction difference | at most 0.000501 ps |
| Absolute timestamp prediction error, median / P99 / max | 25.43 / 155.76 / 171.24 ns |
| Worker elapsed time, median / P99 / max | 953 / 1,737 / 21,644 us |

Prediction errors include startup drift and are not physical alignment
errors. The longest worker duration includes any task preemption. No FTM
failure, panic or watchdog was logged during this healthy boot. The final
snapshot ended on a complete report, so no trailing report was omitted.

The model expired during the four-second input pause. Attempt 127 was
rejected as stale; eight fresh reports made attempt 135 valid. During
the requested disconnect, attempt 705 had already been captured under
generation 2. The disconnect happened before its model evaluation, so
the association guard correctly rejected it. Reports under generation 4
reacquired validity at attempt 713, again after eight fresh reports.
Both responder wraps occurred without a model rejection.

Native replay receives this association invalidation from the logged
disconnect and subsequent raw generation change, independently of the
firmware status being checked. A replay of timestamps alone would accept
attempt 705 because it cannot see the asynchronous disconnect; the live
analyzer explicitly models this external invalidation and retains the
rejected report. Queue-age or other unexplained differences still fail.

## Restored state

The normal endpoint image was restored and flash-verified, SHA256
9e19e9173b84b3d86ae9a3a00112425d836fbe45217bae2b8037c3eb0681a985.
It retains the earlier rollover fix and scope output; raw/model diagnostics
and automatic rejoin self-test are disabled. The first restored boot had
seven failed FTM sessions and no successes. One restart of the same image
then produced 53 successful sessions and zero failures in the saved health
snapshot. Both boots report ELF identity ae376b2c0... . Logs and counts are
in `build-ftm-live/restoration-health.json`. This does not resolve the
startup intermittency, but confirms current ranging recovered.

The bridge and responder images, scope settings and clock discipline were
unchanged. All source changes remain uncommitted. Diagnostic logs, native
executables, builds, image hashes and tap captures are in `build-ftm-live/`.

## Remaining integration

No FTM-driven hardware output or FTM servo is enabled. The remote epoch
still needs a genuine responder boot/coarse anchor. Next implement the
live fine-resolution MAC time source, then connect the P4/upstream mapping
and source validity through the vendor IE before scheduling independent
outputs and measuring their alignment. Relative timestamp prediction
errors cannot substitute for that oscilloscope test.

Actual responder reboot, long outages, upstream clock changes and audio
load remain separate hardware tests. The integer arithmetic currently
rejects epochs beyond INT64_MAX/4 ps, about 26.7 days; production uptime
requirements need an explicit epoch-rebasing design.
