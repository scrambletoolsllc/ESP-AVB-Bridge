# MAC transition diagnostic review, 2026-09-24

This review covers the local C6 diagnostic and its analysis, not the
unimplemented FTM servo or end-to-end AVB synchronization accuracy.

## Findings and changes

1. The first direct sampler still placed a MAC-address load instruction
   inside the timing bracket. Inline assembly now enforces four consecutive
   peripheral loads with early-clobber outputs and a memory clobber. Both
   addresses are prepared before the first read. The linked ELF check
   rejects the old sequence and accepts the new one. No function call,
   branch, result store or arithmetic remains inside the bracket.
2. The task-only sampler used SAFE critical-section wrappers that checked
   ISR context unnecessarily. Normal task wrappers retain exclusion
   without those checks. Pointer lookup, stack handling, critical entry/
   exit, quantization correction, interval fitting and logging remain
   outside the four-read bracket. They still consume CPU time.
3. The original interval omitted the final counter's fractional tick.
   Its lower bound now includes one additional 25 ns tick. Native tests
   exercise a fractional edge, equal quantized reads, negative offsets and
   multiplication near the 32-bit MAC rollover.
4. The analyzer could omit violations from rounds with inconsistent
   intersections. It now reports all violations and unusable rounds,
   matches the firmware's integer midpoint, rejects malformed/missing/
   duplicate/mixed-boot records, and checks observation accounting.
   Full validation requires 120 consistent rounds and normal completion.
5. A short modulo-counter bracket could conceal a long interruption.
   An outer wall-clock gate now rejects observations taking over 100 us,
   below the 1.5 ms MCPWM period. Backwards MAC observations within or
   between attempts abort the experiment rather than mixing generations.
6. The first reviewed run completed 120 rounds but had three unusable
   rounds with no training or held-out transitions. It was correctly
   rejected. Fixed sampling cadence can repeatedly miss the MAC boundary.
   A reproducible, bounded 0–31-iteration delay now varies observation
   phase outside the critical section and four-read bracket. This is
   deliberate test coverage, not extra code in the measurement bracket.

## Hardware and compiler assumptions reviewed

- Both addresses are aligned 32-bit peripheral registers. The linked
  SDK MAC getter reads 0x600ad000; startup direct/API bracket checks pass.
- MCPWM is configured for fixed UP mode, 40 MHz, period 60,000 ticks.
  The private helper uses the allocated timer's actual group and index.
  Its next-count correction matches the selected C6 SDK HAL. It does not
  allocate an output generator or change a GPIO route.
- The C6 manual describes an in-order CPU and guaranteed memory ordering
  in section 1.15.1. The read-only sequence has no pending configuration
  writes between samples. This supports the ordering assumption, not a
  calibrated bound on peripheral read latency. See the
  [C6 TRM](https://documentation.espressif.com/esp32-c6_technical_reference_manual_en.pdf).
- The selected SDK's FreeRTOS critical section raises the interrupt
  threshold and restores nesting state. It is not treated as proof that
  every higher-priority interruption is impossible; bracket gates remain.
- The sampler resides in IRAM. The direct bracket has no flash call or
  floating-point instruction. CPU frequency is fixed at 160 MHz and
  dynamic power management is disabled in the tested configuration.
- MCPWM wraps within a sample are rejected. Phase is unwrapped around a
  reference modulo 1.5 ms; absolute epoch reconstruction is not provided.
- The experiment stops and releases its extra timer. The separate scope
  output and normal application continue. This is default-off bench code.

## Limits of assurance

Four peripheral loads do not mean four CPU cycles. Bus latency, clock
domain crossing and fixed MAC/FTM timestamp bias remain uncalibrated.
Repeated local intervals do not establish independent phase accuracy or
RMS jitter. The updated quantization allowance must not be omitted when
comparing with earlier 225 ns figures.

This review does not cover a live 71.6-minute MAC rollover, forced hardware
clock reset, all power modes, actual admitted audio traffic, responder C6
replication, or independent end-to-end clock accuracy. Those are separate
acceptance tests before production servo use. No hardware floor or global
optimality of this measurement method is claimed.

## Evidence

Build/flash logs, linked disassembly, old/new instruction checks, firmware
images/hashes and both reviewed run logs are under build-mac-transition/.
The first reviewed run is endpoint-audit.log / audit-summary.json and
must not be labeled a passing run. The phase-varied run is
endpoint-dither.log; its final result must be read from dither-summary.json.
Eleven analyzer tests and the native quantization/overflow checks pass.

## Completed rerun

The phase-varied run completed 120/120 usable rounds over 276.661 seconds,
with 12,096 accepted transitions, 96 rejected observations and zero
held-out midpoint violations. Every training interval and the combined
interval was 250 ns wide, including the new quantization allowance. The
training midpoint did not change at 25 ns granularity. This passes the
stricter analyzer's local-consistency criteria.

The physical read bracket remained 250 ns despite removal of the address
instruction. That is evidence that this code cleanup did not produce a
measurable bracket reduction at this resolution, not proof of a hardware
limit. There were no logged panics or FTM session failures during this
rerun; all 276 scope pulse post-checks passed. Those post-checks are not
independent cross-board timing measurements.

The diagnostic released its timer and stopped. Active endpoint firmware:
endpoint-dither.bin, SHA256
7640fe90a29f31a6be23b6154b8ed3a736f9da85814b453503db7ad37f37f4e3.
No bridge or responder firmware was changed in this review.
