# Firmware relative clock observer

`components/ftm_clock_model` is a portable C implementation of the relative
FTM model in `tools/ftm_raw_probe/model.py`. It has no hardware, allocation,
logging, or locking calls. One worker owns its state. Inputs are bounded to
16 entries per report, with 32 report medians in the moving fit. It predicts
each report using only prior reports, then refits for publication.

Enable `CONFIG_FTM_RAW_PROBE` and `CONFIG_FTM_LIVE_MODEL` in the isolated
endpoint experiment. The recorder worker evaluates the model before
formatting raw records. The Wi-Fi report callback only makes bounded,
nonblocking copies. `ftm_raw_model_snapshot()` copies the publication under
a short lock and checks its generation and age. Nothing uses this snapshot
to discipline a clock, schedule GPIO edges, or control audio yet.

The relative responder epoch is arbitrary. It is not the P4 or upstream
clock. A responder boot identity, genuine coarse anchor, live fine MAC
time, source validity and upstream clock mapping are still required.

## Validity gates

- Eight reports before the first valid fit; 32-report window thereafter.
- Two-second maximum report gap and published-snapshot age.
- Association-generation or peer change clears previous history.
- Dropped capture, reordered report, timestamp step, invalid callback read,
  excessive innovation or rate clears the model. Publication is invalidated
  immediately on association events and recorder drops.
- Queue age is at most 500 ms; callback MAC read bracket at most 50 us.
- Callback MAC time is only a freshness check, never a phase observation.
- Remote T1/T4 are modulo 2^48 ps; initiator T2/T3 retain their full width.
- Local/extended epochs are limited to INT64_MAX/4 ps, about 26.7 days,
  to keep integer intermediate operations safe. Longer uptime is rejected.
- Rate bound is 200 ppm and median prediction innovation bound is 20 us.
  These are rejection gates, not accuracy guarantees.

Status values in `FTMMODEL` are 0 accepted, 1 malformed/input age, 2 local
step, 3 remote step, 4 stale/reordered, 5 rate, 6 innovation, 7 recorder drop.
The fields after the marker are attempt, status, accepted entries,
prior-fit prediction flag, rate ppm, median error ps, maximum absolute
error ps, published validity, remote wraps, and elapsed computation us.
Elapsed computation includes task preemption and excludes log formatting;
it is not a CPU-cycle benchmark.

## Reproduction

From the repository root:

```sh
mkdir -p build-ftm-live
cc -Wall -Wextra -Werror -fsanitize=undefined \
  -I components/ftm_clock_model/include \
  components/ftm_clock_model/ftm_clock_model.c \
  tools/ftm_clock_model/test_core.c -lm -o build-ftm-live/test_core
build-ftm-live/test_core
cc -Wall -Wextra -Werror -fsanitize=undefined \
  -I components/ftm_clock_model/include \
  components/ftm_clock_model/ftm_clock_model.c \
  tools/ftm_clock_model/replay.c -lm -o build-ftm-live/replay
python3 tools/ftm_clock_model/compare.py \
  build-ftm-raw/fixed-complete.log build-ftm-live/replay
python3 tools/ftm_clock_model/analyze_live.py \
  build-ftm-live/endpoint-restart2.log build-ftm-live/replay --require-self-test
```

Native tests cover both counter widths, stale/generation/peer/drop reset,
malformed input, rate/innovation/step rejection, and reacquisition. Replay
compares the C implementation with Python against recorded reports. The
live analyzer also compares firmware decisions and printed predictions
with native C replay. It explicitly records skipped self-test inputs and
an unfinished trailing report; it does not remove rejected complete reports.

`CONFIG_FTM_LIVE_MODEL_SELF_TEST` is diagnostic only: pause model input
between 60 and 64 seconds after its first report, then request one Wi-Fi
disconnect after 360 seconds. It repeats on every boot. Restore an image
with this option disabled after the test. Ranging continues during the
input pause, and existing beacon discipline remains active throughout.

Host replay evaluates at callback completion time. Firmware additionally
checks worker queue latency and current association state. The live
analyzer derives association invalidations from logged disconnects and
subsequent raw generation changes, independently of model status. Native
replay applies that guard before evaluating an old queued report. It
cannot reconstruct worker queue latency; unexplained differences fail
the comparison and require investigation against the serial log.
