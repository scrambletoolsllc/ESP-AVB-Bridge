# Scope timing output

Enable CONFIG_CLOCK_SCOPE_PROBE on the bridge P4 and standalone endpoint
C6. This is not the onboard coprocessor diagnostic. Outputs are P4 GPIO45
and endpoint GPIO18. Both are active-high 3.3 V, approximately 1 Hz, with
rising edges scheduled at integer seconds of each device's current PTP
clock. A 40 MHz GPTimer alarm drives the edge through ETM. The ISR only
wakes the diagnostic task. The task clears the pulse about 10 ms later;
falling edges and pulse widths are not accuracy measurements.

On the Waveshare P4-WIFI6-POE-ETH, GPIO45's VDDPST_5 bank is supplied
by LDO4. The diagnostic acquires LDO4 at 3.3 V before configuring the
pin and retains that supply for its lifetime. This is board-specific;
check the schematic before enabling this diagnostic on another P4 board.

The component defaults off. It starts 30 seconds after boot, retains the
normal AVB firmware, and does not change beacon/FTM servo selection.
The endpoint samples a coherent affine clock snapshot and brackets a raw
SYSTIMER capture under the timer driver's lock. Clock conversion runs after
the bracket. This requires the shared esp_ptp coherent snapshot backend.

Clock observations are bracketed by raw timer reads, with the best of
four reads selected. Brackets wider than 10 us are rejected. Two samples
10 to 200 ms apart estimate the local rate. Rates outside nominal +/-1000
ppm and scheduling horizons outside 5 to 40 ms are rejected. One-shot
alarms have at least 1 ms programming margin. Invalid observations can
suppress pulses; missing pulses do not imply a failed oscilloscope.

SCOPE_EDGE fields: sequence, GPIO, intended PTP ns, alarm ticks, pre-read
bracket ns, post-read bracket ns (zero if unavailable), scheduling horizon
ns, preceding rate-interval deviation from nominal ns, reconstructed edge
error ns, post-check valid. The last flag checks pad-high readback and
short-interval clock consistency. It does NOT certify upstream lock or
absolute accuracy. The reconstruction interpolates between pre/post
anchors. A servo change within that interval can invalidate an affine
interpretation without being conclusively detected. Local quantization,
read brackets, GPIO/ETM propagation, instrument skew and extrapolation
error remain in the measurement budget. INT64_MIN means unavailable error.

Measure rising edges. Start at 5 ms/div to find both boards, then zoom in.
Do the same-signal two-probe check before cross-board measurements. The
scope sees physical output separation, which includes pulse scheduling
error, not just clock offset. Current firmware remains beacon-disciplined.
Do not present this as validated FTM synchronization or sub-microsecond
accuracy. Source identity/validity must be checked separately in logs.

Build artifacts/configs/serial logs are in ignored build-scope/. Endpoint
build uses an isolated application copy and the normal shared components.
Restore normal images from /home/dev/ftm-validation-20260921/build-bridge/
and build-endpoint/ when this diagnostic is no longer needed. Coprocessor
firmware and P4 staging partition are not changed by this test.

Arithmetic test:

```
cc -Wall -Wextra -Werror -fsanitize=undefined -I components/clock_scope_probe tools/clock_scope_probe/test_math.c -o build-scope/test_math
build-scope/test_math
```

`rigol.py` has fixed bench address 192.168.4.78 and validates a DHO804
identity. `status` only reads; `compensation` configures a 200 us/div
square-wave check; `timing` configures a 5 ms/div rising-edge acquisition.
It neither changes firmware nor performs calibration.

The P4 revision 1.3 bench cannot use the SDK's native Ethernet PPS GPIO
route, which is exposed for minimum revision 3.00 or later. A tested native
routing experiment produced no periodic signal and was removed. Continue
using the scheduled diagnostic and include its capture/scheduling error.

If the existing scope-specific gateway route stops answering SCPI but the
on-link path works, `capture.py --direct` sets SO_DONTROUTE on that socket.
It does not change system routes. Verified the expected scope identity and
five paired acquisitions using this option on 2026-09-25.
