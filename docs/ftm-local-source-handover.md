# Local-source handover

The bridge already originates wired Sync when its own clock wins selection in
a gPTP build. Its FTM publisher previously required a received upstream Follow_Up,
so AP Announce could advertise the bridge while the radio had no matching timing.

The downstream timing reader now selects a separate local hardware-clock
snapshot when the local clock wins. The daemon originates its timestamp and
Follow_Up template from the running hardware clock, retaining its oscillator trim.
It supplies zero upstream delay and zero initial correction; radio departure
mapping still accounts for elapsed time and the radio-to-host rate ratio.
The received-observation API retains its original meaning. Local fallback does
not make an upstream observation valid or imply external traceability.

Source changes invalidate both snapshots and retire the mapping generation.
An expired received Sync does not enable fallback while the upstream Announce
still selects that source. Snapshots expire at 500 ms. The software-clock endpoint
and priority-255 clocks do not originate these hardware-root snapshots.

This closes one origination gap, not the complete role state machines. General
per-port selection, local ClockSource time-base change metadata across repeated
roles, Sync receipt timeout selection, and final-standard review remain
open. The local source currently uses the existing zero-initialized information
TLV template. It must not be described as complete ClockSourceTime behavior.

Native tests exercise actual publisher/readers, timestamps, identity, retained
trim, separation from received timing, freshness boundaries, source handover,
root eligibility and clock-read failure. Both target builds pass. Hardware test
results are recorded separately after the finite diagnostic completes.

## Hardware evidence, 2026-09-25

The finite test discarded 24 Announce messages and then 64 Sync/Follow_Up
messages. Independent taps verified upstream transmissions during both windows;
the bridge inbound tap was enp1s0f2. Local selection occurred at 16:42:53 UTC,
endpoint readiness returned at 16:42:58, MOTU reception resumed at 16:43:14,
and readiness returned at 16:43:22. Sync loss cleared readiness at 16:43:28;
it returned at 16:43:31. Serial event timestamps have one-second resolution.

All 85 scope acquisitions were paired and within 1 microsecond: -671.339 to
+700.275 ns, absolute p95 646.919 ns, median 151.030 ns. There were no missing
crossings, empty records, rejected arming attempts, or integer-second mismatches.
Sampling was 3.2 ns; no probe correction was applied. Settled local-root operation
had 13 pairs, -51.383 to +510.962 ns. The source was then the bridge, not MOTU.

All 316 management pairs completed. Local-root and restored-MOTU paths matched.
The first management invocation failed discovery during startup and is preserved.
The retry began during Announce suppression but before Announce receipt expired;
seven queries in that pre-expiry window confirmed MOTU. The initial analyzer
expected pre-suppression queries and flagged missing baseline coverage. Its output
is preserved; the corrected window ends before actual local selection and uses
both source snapshot and management evidence. No measurements were discarded.

Artifacts are under build-ftm-discipline/local-source-probe-*. The diagnostic
bridge image is 16fd43f47b1b56761fd7a2dbc313d2cbf92912721ec4d6774bdbdf79874944c0.
The unchanged endpoint is 99ded9bc8de4c04ef92ba1b81f4ad931640cfa4d3e3186e27eb3476407554974;
the unchanged radio is 3b4f997bfd2c9298911876e8663dfc6f76f770478e70af61587656abc906a928.
The diagnostic is disabled in the restored normal build.


## Eligibility review correction

The initial follow-on review incorrectly proposed suppressing Announce for
priority 255. That change was corrected before any such image was deployed.
Announce still participates in selection without an eligible clock;
[IEEE maintenance request 159](https://www.ieee802.org/1/files/public/maint/requests/maint_0159.pdf)
confirms this distinction. Local Sync is suppressed, timing admission rejects a
selected priority-255 vector, and status does not call that vector a valid clock.
The finite no-root test verified Announce/capability continuity and absence of
local timing. Full Sync receipt timeout selection remains an independent gap.
