# Proposed internal clock-mapping contract

This is an implementation contract for the next mapping work, not a wire
format or a claim of IEEE 802.1AS conformance. The production FTM servo is
still disabled. Bench evidence is in the shared-edge results document.

## Domains and identity

Keep five domains explicit: upstream synchronized time, P4 raw GPTimer,
bridge C6 raw GPTimer, bridge C6 MAC/FTM counter, and endpoint local time.
AP TSF is not interchangeable with the MAC/FTM counter. Each raw mapping
belongs to a boot identity pair and an acquisition generation. A snapshot
also names the selected upstream source and its time-base generation.

Use integer anchor pairs plus a bounded relative-rate representation.
Avoid converting full-epoch picoseconds to floating point. Extend truncated
timestamps only against a fresh anchor of the same peer and generation;
reject ambiguity at half a wrap. A report token is only unique within a
session and peer. It is not a persistent measurement identifier.

## Shared-edge acquisition and recovery

The P4 owns GPIO6 pulse generation. Before the first pulse, it sends an
arm request containing its boot identity and a new generation. The C6
clears capture state, records that generation, and acknowledges its own
boot identity. The P4 emits no pulse until that acknowledgment arrives.
Both sides number captures from the same initial sequence.

Preserve the ETM hardware latch before any software timer capture. Publish
capture records with generation, sequence, raw edge ticks, bracketed clock
anchor and quality flags. A missed, extra, or overwritten edge invalidates
the acquisition; restart the handshake instead of matching nearest times.
RPC arrival timestamps are never phase anchors. Bound acquisition timeout,
maximum age, consecutive missed samples and holdover explicitly.

Learn raw P4/C6 rate over a short moving window. The experiment's four-edge
predictor is a baseline to test, not an accepted production estimator.
Reject excessive brackets, non-monotonic counters, uncertain generations,
and innovation errors beyond the declared budget. Reject an expired model
rather than indefinitely extrapolating oscillator drift.

## Upstream time and publication

Keep P4 disciplined-time anchors separate from the raw-counter mapping.
A source change or clock step invalidates those anchors. A frequency
adjustment must be reflected in subsequent conversion; it must not be
interpreted as a raw oscillator discontinuity. Retain actual upstream
source and correction/rate/time-base information from the PTP daemon.
Do not label locally regenerated time with placeholder upstream fields.

Publish complete immutable snapshots from a task. The FTM callback must
read a coherent snapshot in bounded time without waiting for a preempted
writer. Its code, data and arithmetic helpers must be safe in IRAM/DRAM.
Every callback output needs explicit validity; a skipped callback does
not necessarily remove the driver's reserved vendor IE.

## Quality budget and acceptance

Track clock-read brackets, counter quantization, raw-edge prediction,
anchor age, holdover drift, fixed capture skew and FTM calibration as
separate terms. Fit residual alone is not the uncertainty budget.

The final loaded test measured P4 brackets up to 0.625 us, C6 brackets
0.775 us, and raw next-edge prediction up to 0.676 us. MAC resolution is
one microsecond. Those historical results used a microsecond endpoint timer. The current
endpoint backend uses the 16 MHz SYSTIMER; see ftm-local-clock-results.md.
Those observations do not establish a combined one-microsecond bound,
even before fixed bias and wireless calibration are accounted for.

Independent output-edge comparison against a wired reference is still
needed. Until that test and the full budget pass, expose the mapping as
experimental and keep the established beacon mode available. Implement
mapping validity/recovery and source snapshots before enabling FTM servo
injection. Verify each boundary with recorded counter steps, boot changes,
missing edges, stale snapshots and timestamp wrap cases.
