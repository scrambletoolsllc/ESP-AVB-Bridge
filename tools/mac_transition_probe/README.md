# MAC transition calibration experiment

Default-off `CONFIG_MAC_TRANSITION_PROBE` applies only to ESP32-C6. It
retains normal application behavior and by default requires one free GPTimer in
addition to any scope output timer. It drives no pins and does not alter
the beacon clock or FTM servo.

After 30 seconds it starts a free-running 40 MHz PLL-derived GPTimer.
Each observation captures timer-before, reads the private Wi-Fi MAC
microsecond API twice, then captures timer-after. A private driver helper
places the GPTimer lock outside this bracket. Each critical section makes
one fixed sequence of reads; it never waits for a clock transition.

For adjacent MAC values, offset in 25 ns timer ticks is bracketed by:

```
MAC_after * 40 - timer_after - 1 <= offset <= MAC_after * 40 - timer_before
```

This assumes a fixed unit-rate relationship between the two clocks and
that the readable MAC counter represents the relevant boundary without
unknown variable delay. Fixed MAC/FTM counter bias is not calibrated.
Observed bracket intervals are conditional constraints, not a certified
absolute-error bound. Empty intersections are failures, not estimates.
The extra lower-bound tick covers truncation of the final timer count.
Earlier measurements in the results document predate this allowance.

Each round uses 1024 training attempts and 1024 held-out attempts.
Attempts with backwards counters, MAC jumps greater than one microsecond,
or brackets over 10 us are rejected. Unchanged MAC reads are counted but
provide no transition. The task yields one RTOS tick every 16 attempts
and pauses one second after each round. After 120 rounds it stops and
releases the timer. The GPIO scope diagnostic continues independently.
An outer wall-clock bracket over 100 us is also rejected, to prevent a
long interruption from hiding a complete MCPWM wrap. A backwards MAC
observation within or between samples aborts the run and releases the
timer; this experiment does not reconstruct a new clock generation.
A bounded, reproducible 0–31-iteration delay varies sampling phase before
each observation, with interrupts enabled. This avoids fixed-cadence
aliasing that left some halves with no detected transition. The delay is
inside the outer wall-clock guard but outside the four-read bracket.

CSV fields following `MAC_TRANSITION`: round, start_us, duration_us,
training transitions, held-out transitions, invalid attempts, unchanged
attempts, training lower/upper ticks, held-out lower/upper ticks,
held-out intervals excluding the training midpoint, maximum midpoint
miss in ticks, minimum/maximum accepted timer bracket in ticks.
An empty population retains integer extrema and must not be analyzed as
a valid estimate. Per-round midpoints use integer ticks in firmware.

Analyze with `python3 tools/mac_transition_probe/analyze.py LOG`.
Run synthetic analysis checks with
`python3 -m unittest discover -s tools/mac_transition_probe -p 'test_*.py'`.
The analyzer rejects malformed, missing, duplicate and mixed-boot rows,
checks attempt accounting, and retains violations from unusable rounds.
`validated_run` requires all 120 rounds, normal completion, nonempty
intersections and no held-out violations. It does not certify accuracy.

The endpoint build uses the existing isolated `build-scope/endpoint`
application, with unchanged codec configuration. Logs and build evidence
are in ignored `build-mac-transition/`. To remove the experiment, unset
its config in that build, rebuild and flash the identity-verified endpoint.
No shared component source or SDK source files are changed; the helper is
included in the driver build only while the diagnostic config is enabled.

`CONFIG_MAC_TRANSITION_MCPWM=y` selects a second experiment using a
40 MHz MCPWM timer with period 60,000 ticks (1.5 ms), without allocating
an output generator or routing any GPIO. Direct counter reads avoid
GPTimer's software-capture overhead. Reject observations spanning the
MCPWM wrap, and unwrap offset intervals around the first observed phase.
Results in this mode describe fine phase modulo 1.5 ms, not a recovered
absolute epoch. A coarse anchor is still required for a usable full clock
mapping. The existing GPTimer scope output remains running in both modes.

`CONFIG_MAC_TRANSITION_DIRECT_READ=y` removes the API calls from the
MCPWM sampling bracket. The selected C6 SDK getter was checked in the
linked ELF: it loads one word from 0x600ad000. Startup checks the direct
read against bracketed API reads before enabling this experiment. The
sampler performs four peripheral reads, then processes the values outside
the critical section. It applies the C6 HAL's next-count correction for
the fixed UP counter and 60,000-tick period. This private register use must
be revalidated after SDK/chip changes. Neither the startup check nor the
interval fit measures fixed bus or FTM timestamp bias.
The direct C6 bracket is now a four-load inline assembly block with
early-clobber outputs and a memory clobber. Both addresses are ready before
the first read. Critical-section calls and processing remain outside it.
The task-only helper uses the normal critical-section API, not ISR-context
detection. FreeRTOS masks ordinary interrupts by priority; higher-priority
interruptions are not assumed impossible and must pass the timing gates.

The bridge responder can use the same component through the coprocessor
component symlink and allowlist. Copy its production sdkconfig into an
isolated build config, enable the three MAC_TRANSITION options, and keep
FTM_CLOCK_PROBE disabled unless specifically testing that separate probe.
The responder's 1000 Hz tick and endpoint's 100 Hz tick produce different
wall durations for the same attempts/yields. Use recorded durations.
Responder replication and the separately observed audio-load failure are
recorded in docs/mac-transition-results.md.
