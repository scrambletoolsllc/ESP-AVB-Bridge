# Local clock mapping, 2026-09-25

Work in progress; endpoint still beacon-disciplined. No end-to-end FTM
accuracy or conformance result.

The shared software clock now reads C6's raw 16 MHz SYSTIMER, retaining
62.5 ns ticks (rounded down to integer ns). State reads/writes use a short
critical section. Offset/rate updates reanchor at one sampled instant.
Holdover rate arithmetic avoids the old large intermediate product.
Native UBSan checks cover continuity, relative-rate behavior, signed
arithmetic, clamping and long holdover. Both C6 and P4 builds pass.

`components/ftm_local_clock` is default-off and observation-only. First
attempt bracketed two adjacent MAC reads with full timer reads; measured
interval 1313 ns, rejected. Reversing the bracket using the full timer API
still gave 1188 ns. Both unsuccessful images/logs are retained.

The third version brackets only the SYSTIMER capture strobe/ack with MAC
reads, then copies the captured value outside the bracket. Single-core
critical section prevents another ISR from replacing the latch. It uses
IDF's counter snapshot helpers, leaves timer configuration untouched, and
limits the acknowledgment poll. Training and held-out sample sets check
the interval; poor batches invalidate publication. MAC wrap, freshness,
generation and fractional conversion have native checks. This does not
yet establish an uncertainty budget for old FTM observations or holdover.

First 112 logged batches all valid, interval widths 625..688 ns; midpoint
variation 63 ns. This is repeatability of bounded local reads, not proof
of absolute FTM timestamp accuracy. Mapping acquisition remains separate
from any PTP servo. See `build-ftm-discipline/endpoint-mapping-latch-live.log`
and `tools/ftm_local_clock/analyze.py` for continuing evidence.

The scope output previously included clock-conversion arithmetic inside
the read bracket. Moving it out reduced C6 brackets from 7900 to 2750 ns.
A further direct hardware-capture version is built, pending flash/check.
Scope scheduling, read brackets and channel/probe uncertainty must be
included before claiming tight clock alignment.

Fresh six-megabyte P4 backup matches the preserved original application
region. Original endpoint two-megabyte backup and every candidate app
are in `build-ftm-discipline`. No commits or SDK blob modifications.
