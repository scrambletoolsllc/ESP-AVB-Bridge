# FTM clock discipline status

Updated 2026-09-25. The bridge and wireless endpoint experimentally transfer the
MOTU-selected time through hardware-timestamped FTM exchanges. Private beacon
timing does not drive this path. **Sub-microsecond output-edge alignment has been
measured; complete 802.1AS operation has not been established.** Wireless
`asCapable` remains false.

## Latest verified behavior

The final IEEE 802.1AS-2020 text and Cor 1-2021 have now been checked clause by
clause against this path; the table is in `ftm-final-standard-verification.md`.
Four deviations were found in application code and fixed: the VendorSpecific IE
prefix now carries OUI 00-80-C2 (12.5.1.4.1), the gPTP-capable TLV and its
interval request use tlvType 0x8000 (10.6.4.4, 10.6.4.5), gPTP-capable interval
requests faster than the supported maximum select the closest longer supported
interval (10.4.3.2.2), and the Follow_Up inside the FTM IE carries a per-port
sequenceId while measurements pair by FTM dialog token (10.5.7, 11.4.2.8). The
12.3/12.4 asCapable determination is now implemented on the STA port and drives
`GET_AVB_INFO.asCapable`; it evaluates FALSE on this bench because the SDK never
grants a three- or two-frame burst. The remaining conformance gaps are the SDK
items in the same table.

Sync receipt expiry now participates in selection on the current bootstrap path.
A complete accepted Follow_Up or FTM observation renews a separate monotonic timer;
repeated Announce and an incomplete two-step Sync do not. FTM observations carry
their interval and receipt time, so expired queued observations cannot renew it.
The daemon bounds its wait by the receipt deadline. Malformed gPTP Follow_Up
information is rejected before clock adjustment.

A forced four-second timing outage, with Announce still arriving, produced four
wired expirations at 375.039–376.979 ms. Downstream Announce changed to the local
clock, retried the upstream source on subsequent Announce, and returned to MOTU
after Sync reception resumed. All 113 captured Announce sequences were contiguous.
The 90-pair scope run had no missing edges: 88 pairs were below 1 us, with a maximum
of 1.058 us. One AVB_INFO query timed out; 316/317 query pairs completed. These
failures are retained separately from the passing receipt/selection checks.


Root eligibility now gates locally originated Sync and wireless timing admission.
A selected priority-255 vector cannot refresh FTM timing or report a valid received
clock. Announce remains active, as required for source-selection participation;
[IEEE maintenance request 159](https://www.ieee802.org/1/files/public/maint/requests/maint_0159.pdf)
explicitly distinguishes this from clock eligibility. Queued AP Announce work now
carries the timing-source generation and is rejected after source invalidation.

A temporary priority-255 bridge test recorded 18 Announce and 18 capability
messages on each link during the guarded no-root interval, zero wired Sync/FU,
and an unchanged valid FTM payload counter across 15 radio samples. All 269
management pairs succeeded. One startup Announce packet (sequence 4) was absent
from the Linux peer capture, before either outage; later sequences were contiguous.
The no-root checks pass, but the complete capture report retains this discontinuity.
Both normal images have been restored; priority-255 remains a diagnostic setting.


The bridge now supplies FTM timing from its running hardware clock when its own
clock wins selection after upstream Announce expiry. This uses a separate source
snapshot, so local fallback never counts as a received upstream observation.
A finite 24-second Announce outage demonstrated local-root acquisition and return
to MOTU. A separate four-second Sync outage preserved MOTU selection and cleared
readiness. All 316 management query pairs succeeded, and all 85 scope pairs were
within 701 ns, including transitions. Settled local-root samples were within
511 ns. Mapping reacquisition still causes readiness gaps; this is not hitless
handover or complete ClockSource/PortSync behavior.


Announce reception now rejects self-originated messages, hop counts of 255 or
more, and stale STA associations. A missing optional Path Trace TLV is accepted;
the relay omits that TLV downstream and management reports an unknown path,
without changing the selected clock identity. This follows the available D8 text
and [IEEE ballot discussion](https://www.ieee802.org/1/files/public/docs2019/as-mangin-sb-comment-258-support-0319-v02.pdf),
pending verification against the final target edition.

A finite eight-second path-omission test preserved MOTU selection and clock
readiness. All 284 management query pairs completed. Path reporting changed from
three clocks to empty and back; the measured reporting delays were 2.66 and
0.54 seconds, consistent with the existing three-second management status cache.
The wire capture contained 87 contiguous Announce sequences. The diagnostic is
disabled again and both normal images are deployed.

The latest deployed bridge and endpoint also reset Sync/Announce interval policies
on profile changes, invalidate cached capability receipt, and retire old policy
and completion tokens. Announce receipt expiry supports the same -24..24 interval
range as the transmitter. Native tests exercise the actual reset and expiry code,
including wrap and stale work. Hardware validation after deployment tested normal
acquisition and steady operation; it did not force a live profile transition.

The endpoint accepts synchronization stop/reset requests only from its bound AP
identity and association. A stop prevents new FTM initiation. The event-loop start
handler checks the policy again, and reports must match the session's association
and policy revision. Stop followed immediately by reset cannot admit an old report.
An already-started exchange may finish; the checks are not an atomic transaction
with the radio driver. Reconnect and peer identity replacement retire old policy.

A finite bridge-originated hardware test demonstrated:

- Wrong-identity and unsupported-rate requests left FTM active.
- During the guarded stop windows there were no new session starts or reports;
  the responder's valid/invalid callback counters also remained constant.
- The unchanged request preserved the stop. Reset restored discipline in about
  two seconds, measured with one-second-resolution host logs.
- All 23 management query pairs during the stop completed with MOTU selected and
  the MOTU → bridge → endpoint path preserved.

The AP also has an independently tested per-association Follow_Up stop/reset gate.
That gate suppresses our timing payload; native FTM reports continue if the
initiator keeps requesting them. It is not proof of native responder cancellation. Whether ordinary ranging may
continue after gPTP timing is stopped needs final-standard review; continued ranging
alone is not asserted to be a conformance failure.

Only default log sync interval -3 and stop are supported, with reset 126 and
unchanged -128. Other optional synchronization rates are ignored. This does not
complete interval management or the PortSync/MD state machines.

The AP now schedules Announce separately for each association. A Linux station
test verified three old-rate transmissions with the new advertised interval
before slowing from one to two seconds, wrong-target isolation, stop, unchanged,
reset and normalization of a faster request to the supported one-second rate.
All captured Announce sequences were contiguous and retained the MOTU identity.
The Linux station was a control peer, not a second FTM initiator.

A finite wired receive-loss test discarded eight Announce messages, recovered,
then discarded 64 Sync/Follow_Up messages. Independent tap capture confirmed the
switch continued sending them. Announce expiry changed the downstream selection
and path to bridge → endpoint. Sync-only loss cleared endpoint readiness while
preserving MOTU selection and the three-clock path. Automatic recovery took about
eight seconds after Announce reception resumed and one second after Sync resumed,
using one-second-resolution logs. All 285 management query pairs completed.

This test exposed provisional AP control transmission before radio association
reconciliation, including a startup sequence restart. A follow-up fix gates AP
control publication and reception until reconciliation. Native tests and both
builds pass. Hardware startup captured 77 Announce and 77 capability messages,
each sequence starting at one after reconciliation without gaps or restarts.
The original source-loss report retains its sequence-discontinuity failure.

## Physical measurements

| Run | Paired edges within 1 µs | Measured range | Absolute p95 | Scope |
| --- | --- | --- | --- | --- |
| Final-standard images, loaded (Class B AAF, 4000 pps) | 70/70 | -480 to +643 ns | 482 ns | 283,667 AAF packets on the talker-out tap and 283,668 on the switch-to-bridge tap in the scope window, zero sequence discontinuities, zero capture drops; management 137/143 AVB-info and 138/143 path replies (6 and 5 timeouts), all replies MOTU with the three-clock path; no readiness loss or holdover; 23 playout re-seeds and 7-9 EMAC DMA misses per 10 s remain |
| Final-standard wire fixes, all three images updated | 35/35 | -325 to +641 ns | 556 ns | Unloaded, first boot after update; 144/144 AVB-info and 144/144 path replies, all MOTU with the three-clock path, asCapable reported false (flags [6]) |
| Normal Sync receipt/deadline build | 35/35 | -429 to +759 ns | 658 ns | 143/143 management pairs; no settled receipt timeout |
| Sync receipt loss/recovery, including transitions | 88/90 | -443 to +1058 ns | 879 ns | No missing scope edges; 316/317 management pairs |
| Sync receipt baseline before deadline-wait refinement | 40/40 | -361 to +700 ns | 619 ns | 159/159 management pairs |
| Normal root-presence/queue fixes, MOTU selected | 35/35 | -156 to +523 ns | 522 ns | 143/143 management pairs; both normal images deployed |
| Normal local-source build, MOTU selected | 35/35 | -303 to +930 ns | 779 ns | 143/143 management pairs; 35 matching integer seconds |
| Local-source handover diagnostic, including outages | 85/85 | -671 to +700 ns | 647 ns | 316/316 management pairs; 13 local-root steady samples within 511 ns |
| Announce fixes, after switch recovery | 29/30 | -320 to +1052 ns | 866 ns | Unloaded, all 95 management query pairs completed |
| Optional path omission/restoration | 60/60 | -373 to +943 ns | 629 ns | No missing pairs; two arming attempts rejected |
| Latest reset/timeout fixes | 35/35 | -535 to +647 ns | 646 ns | Unloaded, all 95 management query pairs completed |
| Loaded run before reset/timeout fixes | 70/70 | -390 to +746 ns | 651 ns | 275,710 AAF packets captured on each wired leg during scope window |
| Startup publication fix | 60/60 | -438 to +680 ns | 648 ns | Unloaded, second associated control peer |
| AP Announce interval test | 50/50 | -491 to +754 ns | 620 ns | Unloaded, second associated control peer |
| Source loss and recovery | 67/75 | -267 to +3494 ns | 2485 ns | Includes deliberate Announce and Sync loss; no missing pairs |
| Recovered tail of source-loss test | 36/36 | -267 to +676 ns | 620 ns | Subset of preceding run |
| Normal images after restoration | 25/25 | -376 to +616 ns | 539 ns | Unloaded, all 80 management query pairs completed |
| Latest endpoint stop/reset and recovery | 70/70 | -715 to +820 ns | 715 ns | Unloaded, includes eight-second initiation stop |
| AP stop/reset, once endpoint pulses began | 54/54 | -267 to +843 ns | 641 ns | 16 earlier acquisitions had no endpoint pulse |
| Prior loaded cadence validation | 65/65 | -476 to +850 ns | 780 ns | Earlier firmware, audio traffic and management load |

These are finite measurements between bridge GPIO45 and endpoint GPIO18, without
probe/cable skew correction. The latest run sampled at 3.2 ns. They do not measure
absolute error against an independent MOTU hardware time output, establish a
long-term bound, or prove audio sample-clock synchronization. Two simultaneous
FTM initiators remain untested. The loaded run covers the startup publication fix;
the later reset/timeout and Announce qualification changes have unloaded
normal-operation regression runs. The latest 1.052 µs sample rules out claiming
a demonstrated universal sub-microsecond bound.

The first normal-image recovery attempt hit a switch timestamp fault: captured
MOTU Pdelay messages reported about 83–91 ms turnaround while request/response
frames appeared within tens of microseconds on the taps. That scope run had
30 missing endpoint crossings and is retained. An authorized five-second switch
power cycle restored 30–35 µs reported turnaround, valid link delay around
435 ns, and endpoint acquisition without another firmware change. The recovered
measurement is listed separately above.

The startup-fix management run had 213/215 successful query pairs, with two path
timeouts. All successful identity/path responses selected MOTU with the three-clock
path. Do not interpret this as lossless management or audio operation.

The loaded run completed 167/170 management query pairs (one AVB-info timeout,
two path timeouts). Both wired AAF captures had contiguous sequences throughout
the scope window; the complete capture reported one flushed packet on the
bridge ingress tap. Endpoint playout repeatedly reset, so this is a clock
discipline result, not clean audio acceptance. The first connection attempt
timed out and was cleaned up; the retry connected. Audio was disconnected after
the finite run and zero remaining talker connections were confirmed.

## Concrete remaining work

- Complete per-association PortSync/MD roles and source/role handover behavior;
  logical identities and lifetime admission alone are insufficient.
- Complete local ClockSource time-base change metadata and per-port roles. Local
  hardware-root FTM origination and recovery are now measured, but the information
  TLV still starts from the existing zero-initialized template. Announce remains
  active for root-ineligible clocks; local Sync suppression is now verified.
- Complete general per-port Announce information and PortSync state machines.
  Sync receipt expiry now changes selection on the existing bootstrap path;
  this does not establish the full multi-port implementation or all interval
  management and stop/reset interactions.
- Remove diagnostic startup delay and core-audit work from the operational
  mapping path. Initial Announce currently precedes usable FTM mapping, causing
  acquisition timeouts before lock. No deadline was extended to hide this.
- Extend source/role handover validation. AP Announce interval scheduling is
  deployed and bench-tested, with native stale-work and source/path-change tests.
  STA/wired Announce policy and complete interval state-machine behavior remain open.
- Final-standard verification is complete for the clauses this path exercises
  (`ftm-final-standard-verification.md`). Remaining open items there are the
  per-association PortSync/MD state machines and the SDK-dependent rows.
- Obtain supported SDK access to two/three-frame ASAP grants and complete grant
  metadata. This SDK rejects explicit frame counts two and three.
- Replace the private, exact-library diagnostic retention hook with a supported
  API for usable timestamp/IE reports when derived RTT is nonpositive.
- Resolve legacy TM support, AP peer capability visibility and per-peer native
  responder control with Espressif. No incapability is inferred merely from the
  absence of a public API.

The vendor evidence bundle is local and **unsent**:
`build-ftm-discipline/vendor-evidence-20260925.zip`.

## Evidence

- `build-ftm-discipline/sync-receipt-probe-result.json`
- `build-ftm-discipline/sync-receipt-probe-scope-summary.json`
- `build-ftm-discipline/sync-receipt-probe-edge-seconds.json`
- `build-ftm-discipline/sync-receipt-native-tests.log`
- `build-ftm-discipline/sync-receipt-images.json`
- `build-ftm-discipline/sync-receipt-normal-scope-summary.json`
- `build-ftm-discipline/sync-receipt-normal-management-summary.json`
- `build-ftm-discipline/sync-receipt-normal-edge-seconds.json`

- `build-ftm-discipline/root-ineligible-result.json`
- `build-ftm-discipline/root-egress-native-tests.log`
- `build-ftm-discipline/root-egress-images.json`
- `build-ftm-discipline/root-egress-normal-scope-summary.json`
- `build-ftm-discipline/root-egress-normal-management-summary.json`
- `build-ftm-discipline/root-egress-normal-edge-seconds.json`

- `docs/ftm-local-source-handover.md`
- `build-ftm-discipline/local-source-probe-result.json`
- `build-ftm-discipline/local-source-probe-scope-summary.json`
- `build-ftm-discipline/local-source-probe-edge-seconds.json`
- `build-ftm-discipline/local-source-native-tests.log`
- `build-ftm-discipline/local-source-normal-scope-summary.json`
- `build-ftm-discipline/local-source-normal-management-summary.json`
- `build-ftm-discipline/local-source-normal-edge-seconds.json`

- `build-ftm-discipline/announce-peer-result.json`
- `build-ftm-discipline/announce-peer-scope-summary.json`
- `build-ftm-discipline/announce-peer-edge-seconds.json`
- `build-ftm-discipline/source-loss-result.json`
- `build-ftm-discipline/source-loss-scope-summary.json`
- `build-ftm-discipline/source-loss-scope-phases.json`
- `build-ftm-discipline/association-publish-result.json`
- `build-ftm-discipline/association-publish-scope-summary.json`
- `build-ftm-discipline/association-publish-edge-seconds.json`
- `build-ftm-discipline/association-loaded-result.json`
- `build-ftm-discipline/association-loaded-edge-seconds.json`
- `build-ftm-discipline/announce-source-loaded-clock-results.png`
- `build-ftm-discipline/profile-reset-native-tests.log`
- `build-ftm-discipline/profile-reset-scope-summary.json`
- `build-ftm-discipline/profile-reset-management-summary.json`
- `build-ftm-discipline/profile-reset-edge-seconds.json`
- `build-ftm-discipline/announce-path-result.json`
- `build-ftm-discipline/announce-path-scope-summary.json`
- `build-ftm-discipline/announce-path-edge-seconds.json`
- `build-ftm-discipline/announce-qualification-native-tests.log`
- `build-ftm-discipline/announce-qualification-recovered-scope-summary.json`
- `build-ftm-discipline/announce-qualification-recovered-management-summary.json`
- `build-ftm-discipline/announce-normal-pdelay-check.json`
- `build-ftm-discipline/announce-normal-pdelay-recovered.json`
- `build-ftm-discipline/sta-probe-reconciled-result.json`
- `build-ftm-discipline/sta-probe-reconciled-scope-summary.json`
- `build-ftm-discipline/sta-probe-reconciled-management-summary.json`
- `build-ftm-discipline/sta-probe-reconciled-edge-seconds.json`
- `build-ftm-discipline/sta-policy-native-tests.log`

The first bridge-originated probe aborted safely after startup reconciliation
changed its association generation. Its 65-pair scope run was a baseline only,
not a stop/reset test. The repeated run above waited for reconciliation and
completed the actual requests. Diagnostic request probes are disabled again;
current deployment details and boot recovery are recorded in `project.md`.
