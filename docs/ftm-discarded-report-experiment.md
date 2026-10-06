# Discarded-report clock experiment, 2026-09-25

The exact installed Wi-Fi blob discards both timestamp quartets and vendor
IEs when no raw RTT is positive. Audit artifact:
`build-ftm-discipline/ftm-parse-data.disasm`. Its public vendor getter copies
102-byte entries; the diagnostic statically checks that ABI and requires
the previously audited object SHA256 before linking.

An optional free-hook capture now preserves both arrays before cleanup,
without mutating timestamps, driver state, or report status. A per-session
reset and exact event comparison prevent reuse. Receiver admission still
checks association, token, source, time base, fresh local mapping and rate.
Verbose raw-report logging and RX timestamp wrappers are disabled.

Retention alone did not acquire: quality logs showed corrected RTTs around
-4 to -12 ns with relative radio frequency near -53 ppm. Those estimates
remain physically inconsistent as distances. The experimental signed mode
retains the algebraic two-way estimate, including its sign, down to -25 ns.
That threshold is a diagnostic guard, not a calibrated hardware error bound.
There is no clamping to zero or artificial positive responder offset.

This separates clock-controller testing from positive-distance filtering.
It does not fix the RF timestamp bias, establish range accuracy, provide a
portable SDK solution, or prove 802.1AS conformance. Both diagnostic options
are default off. Independent scope evidence is required before any clock
accuracy claim. Strict nonnegative admission remains available.

Images and logs remain separate in build-ftm-discipline: clean cadence,
retention, quality, and signed experiment. Vendor API retention and burst
controls are still needed for a supported implementation. No external
messages have been sent.

## First physical result

Signed-experiment endpoint SHA
84c22a3892436ed1aeac73d67817a3f6451a5f3637130e364e06fc4c903b0176
acquired at about 07:17:44 UTC. The bridge and coprocessor retained the
FollowUp-mux and clean-callback images. New-boot corrected RTTs crossed zero;
this was not the consistently negative state of the previous boot.

60 paired Rigol DHO804 RAW/WORD acquisitions, 3.2 ns sample interval:
CH2 minus CH1 minimum -539 ns, median +162 ns, maximum +1355 ns;
58/60 within 1 us, absolute nearest-rank p95 979 ns. Both probes 10x.
Artifacts: ftm-signed-scope-fine.json and ftm-signed-scope-summary.json under
build-ftm-discipline. Historical same-pin median channel/probe difference
was +2.56 ns; not subtracted here. This is output-edge alignment relative
to the wired bridge, not a direct measurement of the switch's internal
clock. Pulse-generation and domain-mapping uncertainties remain included.

The two largest errors occurred during bridge mapping gaps. Invalid
source anchors at edge581 and585 reset all history, requiring four new
edges. At edge581 requested trim changed between source snapshots while
the actual hardware rate was separately captured coherently. A pending
fix removes that redundant requested-trim equality test. Hardware addend,
control, source-generation and freshness guards remain. A second change
retains valid raw edge history while rejecting a PTP anchor; a native test
injects a 1s bad reference and verifies it cannot contaminate recovery.

Endpoint timing-readiness status also needs to reflect acquisition and
freshness rather than Announce presence alone. The pending build gates
published clock validity on a fitted, settled update in the same source
and association generation within 375ms. Source discovery remains active.
Further physical measurement and loss/recovery tests are pending.

## Signed-delay context

IEEE maintenance request 375 discusses negative link-delay estimates from
timestamp error and calibration, and proposes a signed meanLinkDelay type:
https://www.802-1.org/items/485/requests/375/pre
It concerns the Ethernet calculation and is a proposal, not evidence that
this FTM implementation is conformant. It supports treating small negative
estimates as a measurement issue rather than unsigned large distances.

The 2019 D8 clause12.5.2.4 chooses forward and reverse minimum-delay pairs
independently for a three-frame burst. The current eight-frame prototype
chooses one minimum-RTT quartet. This difference needs implementation/audit
against the final normative edition alongside the unsupported3/2-frame
negotiation. The draft allows other rate/delay computation methods, but
that is not a conformance determination for this prototype.

## Loaded validation and recovery, 2026-09-25

All results below are paired bridge/endpoint output edges at 3.2 ns sample
spacing, with no channel-skew correction. They do not independently measure
the switch's internal clock or prove protocol conformance.

| Run | Paired/acquisitions | Min / median / max (ns) | Absolute p95 (ns) | Within 1 us |
|---|---:|---:|---:|---:|
| Five-second withheld observations | 90/90 | -887 / 169 / 958 | 693 | 90/90 |
| Class B traffic load | 60/60 | -493 / 22 / 766 | 543 | 60/60 |
| Register-read retries, switch recovery | 60/60 | -576 / 147 / 684 | 576 | 60/60 |
| RPC error guard, loaded | 100/100 | -528 / 106 / 968 | 707 | 100/100 |

Raw files are `build-ftm-discipline/ftm-{loss,audio,retry,rpc-guard}-scope-fine.json`;
corresponding `scope-summary.json` files count missing pairs explicitly.
The deliberate loss setting was disabled and the endpoint reflashed afterward.

Repeated bridge link resets exposed stale MOTU receive timestamps in actual
Pdelay responses. A power cycle through the authorized Shelly outlet cleared
the switch fault; source selection and endpoint acquisition recovered.
The longer load test later exposed an ESP-Hosted NULL response dereference
in the Announce publisher. A guarded count copy and native sanitizer
regression are in `patches/esp-hosted-station-list-null-response.patch` and
`tools/hosted_rpc/test_station_list.py`. The rare missing RPC itself remains
under investigation.

Traffic was approximately 4000 AAF packets/s at bridge ingress. This is a
loaded timing result, not a clean audio result: repeated MSRP admission
failures and endpoint playout resets were observed. Admission accounting
was found to charge the same stream on LeaveAll refresh without releasing
the existing charge; its correction is being separately validated.

## Stable loaded baseline, 08:13–08:25 UTC

The final deployed baseline uses bridge image `d489654b...` and endpoint
image `5ab6bb9c...`, including RPC routing, admission accounting and
mixed-source report guards. The 600-acquisition scope run lasted
11 minutes 26 seconds. It produced 599 paired edges, all within 1 us:
minimum -695 ns, median 138 ns, maximum 991 ns, absolute p95 648 ns.
The first acquisition preceded the endpoint diagnostic output’s first
pulse and has no CH2 crossing; it remains counted explicitly.

The endpoint restart cleared its listener connection. Bridge forwarding
continued, and the Class B listener was reconnected at 08:13:51 UTC.
Restricting the result to full receiver load after 08:13:55 gives 570/570
paired captures within 1 us, with the same extrema and p95. A ten-second
tap capture contains 39,841 AAF packets from the talker and 39,827 entering
the bridge. No RPC/panic errors, admission rejections or endpoint holdover
events occurred during the final loaded interval. The largest interval
between successfully applied observations was 360 ms.

Both devices logged all 662 common pulse target seconds in the settled
08:13:55–08:24:55 interval, without missing or duplicate targets. Host log
time differences were -1..+1 second with median zero, reflecting one-second
log timestamps and serial buffering. This is internal epoch corroboration,
not a second independent precision measurement.

Artifacts: `ftm-final-loaded-scope.json`, `ftm-final-loaded-scope-summary.json`,
`ftm-final-loaded-acceptance.json`, `ftm-final-edge-seconds.json`,
`ftm-final-loaded-traffic.pcapng`, and `clock-validation.svg`, all under
`build-ftm-discipline`. Audio still has packet loss/concealment and playout
resets; healthy reservation and tight timing do not establish clean audio.

## Protocol follow-on regressions, 08:43–08:58 UTC

| Configuration | Pairs | Min / median / max (ns) | Absolute p95 (ns) |
|---|---:|---:|---:|
| Complete path + daemon-owned RX, unloaded | 90/90 | -548 / 137 / 705 | 558 |
| Private beacon timing entirely disabled, unloaded | 90/90 | -476 / 144 / 815 | 607 |
| Independent direction selection, Class B load | 150/150 | -553 / 235 / 798 | 650 |

All captured pairs are within1us, with zero missing pairs. These are separate
runs, not a pooled accuracy distribution. The last run lasted08:55:43.761–
08:58:13.464. Traffic was39843 talker-out and39830 bridge-ingress AAF packets
in10s, endpoint reception approximately4kpps. No FTM readiness drop/holdover
after acquisition; reservation remained code0. Private beacon timing was
ignored, including admission, in the last two configurations.

Important coverage exception: target second2848 is missing from the bridge
pulse log in the loaded run, while the endpoint logged every target. The
scope uses the bridge pulse as its trigger, so150/150 measured pairs does
not establish uninterrupted pulse delivery. The153-second log comparison
has152 common targets, one missing bridge target, no endpoint missing
and no duplicates. This is retained in pair-selection-loaded-edge-seconds.json.
There was no corresponding FTM readiness drop. The pulse scheduler and its
short arming window need separate review; do not label the run lossless.

Independent directional minima were first compared without steering:
63reports,56different forward/reverse indices, estimated phase change
-13..3ns,median0. The optional selection mode then used those independent
minima, with a combined signed-delay guard and the forward packet's own
matched FollowUp. The SDK still grants an eight-frame fallback, so this
algorithm change is not three-frame burst conformance evidence. Both
three-frame and two-frame requests now have explicit INVALID_ARG evidence.

Audio limitation: the C6 avbpll backend returns failure on targets without
APLL, leaving sample-clock rate uncontrolled. Buffer growth and sequence-gap
concealment remain. Stream-reference epoch logs also include concealment
re-seeds, not only actual playout re-gates; do not equate every such log with
a clock unlock. No audio clock backend has been changed in this work.

The subsequent receive-validation build (P4 7e5b0d04..., endpoint31a542ac...)
reacquired after another captured MOTU stale-T2 fault was cleared by an
authorized switch power cycle. Unloaded recovery scope:60/60 pairs within1us,
-624/271/855ns min/median/max, absolute p95709ns, no missing pairs. Separate
63/63 common logged target seconds, no gaps or duplicates in that interval.
The earlier loaded pulse exception remains; this does not erase it.
