# FTS reference review, 2026-09-24

Reviewed abbbe/fts commit `5d6ea2bfcd516473a98f8aebe7daf690eec21b31`.
Reference checkout: `/tmp/fts-review-20260924`. No firmware changes or
external source imports were made during this review.

## Evidence and scope

[Performance report](https://github.com/abbbe/fts/blob/5d6ea2bfcd516473a98f8aebe7daf690eec21b31/docs/posts/20251222-performance-stress-testing.md)
reports one hour of relative pulse measurements between two S3 receivers
following a third S3: average 14 ns, standard deviation 27 ns, reported
P99.9 99.9 ns. It uses hardware MCPWM outputs and SDR edge interpolation;
the author estimates roughly 10 ns measurement error from known-signal
checks. This is evidence reported by the author, not independently reproduced
here. It does not establish alignment to an external AVB time source.
Shared systematic errors can cancel in a receiver-to-receiver comparison.

## Most useful implementation techniques

- `components/dtr/dtr.c` repeatedly brackets two MAC clock reads with fast
  timer reads, retaining observations where the MAC count advances. It
  intersects the resulting offset intervals over 100,000 attempts and uses
  their midpoint. The S3 MCPWM backend reads the counter directly through
  HAL. A 1 us readable MAC count therefore need not impose a 1 us alignment
  floor when its transition timing can be resolved. Transferability and
  fixed read latency need measurement on C6.
- `components/crm/crm.c` models local T2 against remote T1 plus half RTT
  using up to 128 samples from 64-frame sessions. The model estimates both
  phase and relative rate. It uses reference timestamps and slope-minus-one
  arithmetic. Residuals describe fit consistency, not total accuracy.
- Timer period control uses fractional accumulation to alternate integer
  25 ns ticks. MCPWM generates the physical edges; software prepares period
  and phase updates. Our GPTimer-to-ETM hardware output should be retained.
  FTS's GPTimer fallback toggles GPIO in its ISR and does not reproduce the
  hardware-output timing path of the reported S3 measurements.
- Current FTM code has coarse full-MAC-time broadcasts for initial epoch
  selection, beyond the older README/closed issue's startup limitation.
  It separately handles 48-bit responder timestamps and the additional
  32-bit-microsecond MAC rollover. These behaviors need local SDK tests.

## Application to this bridge

The immediate experiment should map C6 MAC transitions to a free-running
40 MHz timer, on both the responder coprocessor and standalone endpoint.
Add bounded acquisition, reject MAC jumps other than one microsecond,
check interval consistency, and measure repeatability under audio/Wi-Fi
load. Avoid transplanting the long calibration critical sections or its
unbounded transition loop into the live audio path.

Then build a separate raw FTM offset/rate model and compare hardware
outputs. Retain the P4/C6 shared-edge mapping, actual upstream source/time
snapshots, and vendor IE work to carry the wired clock relationship.
Finally connect the accepted model to endpoint clock/audio discipline.
Low relative wireless jitter alone does not complete that chain.

The previous 3.950..4.462 ms physical separation measured our existing
beacon discipline and experimental PTP pulse scheduler. It does not bound
FTM capability. The new reference changes the next mapping experiment;
it does not yet justify a nanosecond accuracy claim for our hardware.

Production validity still needs explicit model age, plausible rate,
innovation bounds, generation changes, reboot recovery and long rollover
tests. FTS's R-squared gate alone is insufficient for these requirements.
