# FTM transport audit, work in progress

For the latest deployment, measurements and remaining work, see
[current status](ftm-current-status.md). Dated entries below preserve the
investigation history, including findings superseded by later fixes.

The installed vendor IE patch enables data carriage, not complete 802.1AS
operation. Accuracy and protocol acceptance remain separate requirements.
Target edition in this repository is 802.1AS-2020. The final text and
Cor 1-2021 were checked on 2026-09-25; see `ftm-final-standard-verification.md`,
which supersedes the D8-based rows below where they differ. The public 2019
D8 draft was only a preliminary cross-check:
https://1.ieee802.org/wp-content/uploads/2019/03/802-1AS-rev-d8-0.pdf

Preliminary draft checks, clauses 12.6, 12.7, 12.8:

| Area | Preliminary requirement | Current implementation gap |
| --- | --- | --- |
| FTM negotiation | Single ASAP burst, three frames initially, two on retry | Three- and two-frame requests rejected with ESP_ERR_INVALID_ARG; eight-frame fallback negotiates single ASAP burst, 32 ms duration |
| Cadence | Default log interval -3; corresponding burst duration and minimum frame spacing | FTM-only scheduler now uses a 125000 us esp_timer deadline; explicit frame-spacing control remains unavailable |
| Timing payload | Complete Follow_Up, including common header and information TLV | Actual FTM callback carries upstream FollowUp with mapped residence correction, rate and time-base data; matched receive tokens and physical sub-microsecond edge alignment demonstrated |
| Interval management | Signaling interval requests and supported-value handling | Capability intervals, AP/STA synchronization stop/reset and AP Announce intervals are implemented and bench-tested; complete role/state-machine integration remains open |

Code evidence: `esp_wifi_types_generic.h` documents frame counts
0/16/24/32/64 and burst period in 100 ms units. Runtime logs confirm the
current negotiation. Do not assume setting burst period zero selects ASAP;
capture the request and granted parameters. Do not force unsupported counts
by modifying opaque driver state without validating layout and behavior.

Implemented and bench-tested: upstream source/time-base propagation,
matched receive tokens, hardware mappings with reset/freshness checks,
FTM-only affine steering, observation-loss holdover/recovery, and independent
scope measurements under traffic load. See ftm-discarded-report-experiment.md.

Remaining acceptance items include supported access to usable quartets and
IEs when the ranging filter reports nonpositive RTT, full Signaling and
capability state machines, interval negotiation, domain handling and final-standard audit. Full bounded path trace is now
preserved and appended, with loop rejection and selected-source Announce
timeout/refresh checks. Independent captures at an associated Linux control peer
now verify outgoing Announce identities and paths, including source loss/recovery.
Two simultaneous FTM initiators remain untested. The current receiver uses an exact-blob
retention diagnostic and experimental signed RTT admission. These are
explicit experimental dependencies, not evidence of conformance.

No conformance claim has been made. Prepare a concrete SDK capability
request if the required negotiation cannot be expressed; external messages
are not sent without user authorization.

Edition note: IEEE also lists [802.1AS-2025](https://standards.ieee.org/ieee/802.1AS/11968/)
and a [maintenance revision](https://1.ieee802.org/maintenance/802-1as-2025-revision-timing-and-synchronization-for-time-sensitive-applications/).
The repository target above remains 2020; newer editions do not make the
unapproved 2019 draft a normative conformance reference.

2026-09-25 update: The earlier 07:07 acquisition blocker was isolated to
usable data being discarded by the ranging filter. Diagnostic retention
and signed RTT admission enabled the physical results. Cadence rounding
was corrected with esp_timer. Required three-frame requests remain rejected
by the SDK; the eight-frame fallback cannot establish burst conformance.

08:51 update: the FTM discipline path now ignores the private beacon timing
IE and removes it from request/report admission. Association/session and
source-qualified FTM/mapping checks remain. Fresh boot acquired without
beacon timing; 90/90 scope pairs within1us, -476..815ns, abs-p95607ns,
zero missing pairs (unloaded run). This removes one private transport
dependency, not the discarded-report hook.

A shadow comparison of independent forward/reverse minima over63 reports
found different selected direction indices in56 reports. Estimated phase
change was -13..3ns, median0. No clock steering was changed. This operates
over admitted quartets of the SDK eight-frame fallback, so it is not proof
of three-frame burst behavior. Native tests cover separate minima, remote
counter wrap, unrelated clock epochs, signed combined delay and rate.

The public draft12.4 ties wireless capability to negotiated burst support
and domain/neighbor-capability conditions. Existing ATDECC GET_AVB_INFO
maps asCapable directly from clock_source_valid; this is not sufficient.
Do not infer protocol capability from the scope or FTMREADY. Final-text
verification is especially important for the domain0/FTM case.

2026-09-25 source/status correction: selected Announce identity/path is now
published independently of the FTM consumer-readiness gate. ADP, clock-source
identity, GET_AVB_INFO BTC identity and GET_AS_PATH use selection, not servo
readiness. GET_AS_PATH preserves the full observed chain plus local identity
(max17) and uses exact serialized length. A prior length expression added
two excess bytes; the new sender passes ASan/UBSan tests for1..17 clocks.

Finite five-second observation loss: all271 management samples kept the
MOTU BTC identity and three-clock path, zero response timeouts; readiness
fell and recovered as expected. The separate40-pair recovery scope run
was within1us (-524..686ns), but began after the gap and is not evidence for
the complete outage. LOSS_TEST is being restored off.

Still unresolved: GET_AVB_INFO asCapable is a legacy mapping of consumer
clock validity. It is not a valid protocol capability determination. New
source/status fields do not claim to fix that separate state machine.
Primary reference cross-check for capability receipt/expiry behavior:
https://sourceforge.net/p/linuxptp/mailman/message/51783820/
No reference implementation code has been copied.

2026-09-25 09:38 capability correction: GET_AVB_INFO now uses a separate
as_capable field. Wireless remains false until media support and domain/peer
negotiation are verified. Internal FTM readiness remains independent. Wired
reporting retains the legacy source-validity policy; it is not a completed
capability state machine. Live endpoint responses retained MOTU and the
three-clock path with flags6 while FTMREADY1.

Capability Signaling RX now validates bounded TLVs, domain, target port and
source, and records historical indications on the actual ingress port. A
single host-identity probe reached the bridge and was logged. This proves
decoder reachability only. TX, interval handling, neighbor binding, expiry,
media negotiation and full per-port timing state remain open.

Peer-delay correction audit: the old Follow_Up handler overwrote the Sync
correction accumulator. Corrections now remain within the peer exchange,
using response minus Follow_Up correction, as in public D8 equation11-6.
Native actual-handler tests cover signed corrections, zero and rejected
negative delay while preserving Sync state. Current integer-nanosecond
rounding and unity neighbor rate assumption remain; this is not a complete
peer-delay implementation. Full requester/responder identity, transaction
lifetime, duplicate rejection and concurrent TX timestamp publication still
need work. Cross-check only, no source copied:
https://github.com/richardcochran/linuxptp/blob/master/port.c

09:50 UTC: wired peer transactions now have immutable request timestamps,
full requester/responder port matching, expiry, generation invalidation and
single consumption. Sender and parser native tests pass, including sequence
wrap and publication ordering. Firmware deployed and reacquired MOTU and FTM
without switch reset. Detailed remaining lifecycle and rate-ratio limits are
in peer-delay-transaction-audit.md. This does not enable wireless asCapable
or change the eight-frame SDK fallback limitation.

09:58 UTC: wired delay now uses measured neighbor rate and fractional
corrections. Native +/-100ppm tests expose and remove a1500ns unity-rate
bias in a30ms-turnaround example. Rate is formed from matched T4 and
corrected T3 differences, with peer/lifecycle/gap validation. Final commit
rechecks exchange generation and lifecycle. Hardware reports about+28.7ppm
before discipline and nearzero afterlock. This supersedes the earlier
unity-rate/integer-correction limitations, but does not establish AnnexB
performance or complete asCapable determination.

10:08 UTC: wired asCapable now comes from fresh qualified peer exchanges,
not source selection. Qualification requires valid rate, mean delay<=800ns,
nonself peer, exact peer-message sdoId0x100, current lifecycle and enabled
live Ethernet in domain0. Wireless remains false. Three-interval expiry is
conservative, not the final allowedLostResponses/allowedFaults state machine;
Sync/BTCA gating still needs integration. Native actual-status tests verify
independence from selection and expiry. The bridge has ATDECC disabled, so
its flag has not yet been verified through a live management response.

This deployment encountered endpoint NO_AP_FOUND startup failures. Resetting
only the endpoint with unchanged firmware restored association and FTM
readiness. Failed and recovered logs are retained; cause is unresolved.

10:17 UTC: live capability expiry/recovery test passed. Six omitted bridge
peer-delay requests produced a7.003s wire gap while56 Sync and56 Follow_Up
messages still arrived from MOTU. PDELAY_CAPABLE cleared and recovered as
expected. The scope covered the entire gap:90/90pairs within1us, -527..898ns,
with no missing pulse seconds. All270endpoint management samples retained
MOTU and the complete path. Timing acceptance is not yet gated by capability,
so this is evidence for qualification reporting, not protocol conformance.
Diagnostic config is restored off; normal images are being redeployed.

10:31 UTC: wired qualification now gates received Announce, Sync and
Follow_Up, source validity, and own wired timing transmission. On loss it
invalidates the published timing snapshot and pending two-step state.
Peer-delay traffic remains active for recovery. Selecting a different
upstream clock no longer invalidates the physical peer qualification; an
actual clock step still does. Bootstrap timing handlers reject other ingress
ports, rather than treating them as multiport BTCA.

The repeated six-request outage produced the expected physical/software
behavior: incoming MOTU Sync continued, the bridge snapshot stopped
advancing and became invalid, endpoint readiness dropped into holdover,
and both recovered.100/100 scope pairs stayed within1us (-660..716ns).
Management temporarily selected the bridge root, then returned to MOTU.
This verifies the implemented gate and recovery, not full conformance.
Three-interval expiry still differs from the complete fault-count state
machine, and the Wi-Fi timing path is still an experimental FTM path.

## Neighbor capability receipt, 2026-09-25

A wired received capability indication is now bound to the full ten-byte port
identity learned by peer-delay measurement, the current link/clock lifecycle,
and a nine-advertised-interval monotonic deadline. Valid advertised exponents
are -24 through 24; reserved values cannot refresh state. Sub-microsecond
intervals round upward to the next microsecond, a receiver timer-resolution
limit, not a claim of Annex B performance. Same-clock indications (including
another port on this clock) and nonzero minor SDO identifiers are ignored.

For nonzero wired domains, the capability gate now additionally requires this
fresh bound indication. Domain zero retains the measured-peer compatibility
condition. This is a gate implementation, not proof of complete multi-domain
operation: common peer-delay domain handling and Signaling transmission and
interval requests still need implementation/audit. All deployed bench devices
remain domain zero.

Native tests exercise all 256 interval byte values, exact expiry, refresh,
overflow, lifecycle change, foreign neighbors, actual ingress dispatch, and
actual status publication compiled for domains zero and one. Firmware builds
pass. Wireless received indications remain diagnostic only: the AP needs
per-associated-station port/neighbor mapping, and the injected PTP frame API
currently discards the Ethernet source MAC. Do not bind an AP wireless port to
its wired selected source or claim that receiving any Signaling message makes
FTM media capable. SDK two/three-frame grants and the final clause 12.4 domain
requirements remain unresolved.

## Wireless receive lifetime and sender metadata

The injected receive queue now preserves a copied Ethernet source MAC when
provided by `ptp_inject_received_frame_from()`. The AVB Wi-Fi dispatcher uses
that API; the older API remains available and explicitly marks sender metadata
unknown. Wired receive also publishes its source MAC into the daemon's receive
context. This is transport metadata, not authentication or a neighbor binding.

Per-port queue generations change on link transitions and daemon stop/start.
A generation change during timestamp acquisition rejects publication with
ESTALE, and an older queued generation is discarded when drained. Existing
bounded copying, original timestamp, FIFO and daemon parser ownership remain.
Actual-code ASan/UBSan tests cover sender-buffer ownership, link transition
invalidation, repeated link state, stale queued frames and a transition during
enqueue. Both target builds pass.

This does not yet serialize link events with a frame already in the parser,
nor provide AP per-station association generations. Those are separate remaining
ownership requirements. STA BSSID-to-PTP-port binding and AP per-station mapping
must use this metadata before wireless capability can be asserted. The new
queue firmware is built but not deployed; hardware still runs the measured
bridge early-response fix and unchanged wireless endpoint.

## Associated STA neighbor binding

STA gPTP frames now require Ethernet sender metadata matching the associated
AP BSSID. Association events clear the learned PTP port and capability receipt;
even reconnecting to the same BSSID starts a new association. Startup seeds
association state from the current AP record if association preceded handler
registration, with a generation check against an intervening event.

A path-valid Announce from that AP binds its full PTP source port identity.
Learning is independent of which clock wins selection. Capability Signaling
must then match both that source port and the current associated sender and
receive association. Unknown sender metadata, foreign MAC, foreign PTP port,
unbound neighbor and stale association cannot refresh capability. AP-mode
per-station mapping remains unfinished, and wireless asCapable is still false
pending media negotiation and normative verification. This is protocol neighbor
identification, not cryptographic authentication.

Native tests exercise the actual receive gate, Announce handler, Signaling
branch and queued-frame lifetime, including learning from a valid non-selected
Announce. Bench startup learned generation 1, and an AP restart rebuilt the
neighbor as generation 15 after disconnect retries. Initial management returned
65/65 full MOTU paths. Loaded clock regression follows in the project ledger.

Loaded result after association binding and bridge restart: the final deployed
images maintained 100/100 paired scope edges within 1 us at 4000 AAF packets/s.
Range -868.544 to +878.637 ns, median 263.771 ns, absolute p95 686.521 ns.
All 100 target seconds were present on both pulse logs. No missing/empty scope
record or rejected arming occurred. Management: 237 BTC replies all named the
MOTU, 236 path replies all showed three clocks, and one path request timed out.
This validates the current chain and reacquisition, not full Wi-Fi conformance
or lossless audio. Artifacts have prefix `wifi-neighbor-loaded` in
`build-ftm-discipline`. Media asCapable remains false on Wi-Fi.

Capability transmission and additional normative audit, September 25:
The common encoder now emits a 60-byte wildcard-target gPTP-capable Signaling
message, minor version 1, control field zero and header log interval 0x7f.
The wired bootstrap port transmits immediately and every second while enabled
and linked, independently of peer qualification. Failed sends remain bounded
by that cadence. This is initial-interval transmission, not the complete
interval-request/slowdown/stop state machine. Wi-Fi transmission is not yet
implemented. Native golden-wire and actual-dispatch tests pass.

Public D8 Table 10-9 requires transmitted PdelayResp twoStepFlag TRUE but
ignores that flag on receive. The earlier over-strict receive rejection is
removed; a matched Follow_Up is still required before applying a measurement.
Older common-message marshalling needs a separate audit of minor version,
control fields and the reserved Announce origin-timestamp bytes.

D8 clause 12.1.2 explicitly requires a separate PortSync and MD entity for
each association on a physical Wi-Fi port. The current AP-wide state does
not satisfy this for multiple stations. Clause 5.6 also requires legacy TM
for relay instances and recommends FTM; endpoints may implement either.
This is a final-edition verification item and a supported-SDK API question,
not an established C6 hardware limitation. An unsent vendor question records
it. No final-standard conformance claim follows from the measured accuracy.

Wired capability TX bench verification: 76 captured messages passed independent
raw-byte validation with no sequence gaps; intervals 0.969894 to 1.039896 s,
median 1.000045 s. Four taps reported no capture drops. An unloaded 35-edge
scope check measured -382.919 to +583.395 ns (absolute p95 540.411 ns), with
35/35 paired edges and no missing acquisitions. All 120 management queries
returned the MOTU source and full three-clock path. Artifacts:
`capable-transmit-*`. This tests the new wired transmitter, not Wi-Fi signaling.

Wireless initial capability transmission implementation:
Both AP and STA now schedule their own one-second capability message using
that physical port's identity. A dedicated bounded queue and worker perform
radio queries and unicast sends, separate from the Announce overwrite mailbox.
The daemon never waits on those RPCs. Queue saturation drops that interval's
message. Work expires after one second and is checked against link/daemon
restart generation both before radio lookup and before each send. The STA
queries its current BSSID; the AP sends to its currently enumerated stations.
The wired gate no longer resets the STA bootstrap port's transmit timer.

Actual-code native tests cover cadence on both ports, unicast frame bytes,
initialization failures, copy ownership, queue saturation, AP fanout, failed
radio queries and a link transition during the query. Both firmware builds pass.
This is initial-interval signaling, not complete per-association PortSync/MD
or interval-request negotiation. A transition between the final generation
check and radio submission remains a narrow concurrency limitation, and AP
per-station association epochs remain to be implemented. Wireless asCapable
is deliberately still pending media verification; sending a capability
indication does not itself prove a usable synchronized media link.

Wireless TX hardware result: both receive paths log capability indications at
approximately the expected cadence. The monitor capture contains no matching
Wi-Fi Signaling frames, so receive logs are the current evidence. Loaded scope:
65/65 paired edges within 900 ns, absolute p95 763 ns, no missing pulses.
However, four wired exchanges missed their Follow_Up internally (the first is
present on the tap), and management had five info plus three path timeouts.
A later real Ethernet link-down event caused temporary holdover and automatic
reacquisition. This is functional progress, not a reliability acceptance pass.
Artifacts use `wifi-capable-*`; preserve the logs and capture for diagnosis.

Transmitted-field correction, built but not yet deployed:
Public D8 10.6.2.2.3 and 10.6.2.2.13 specify minorVersionPTP=1 and control=0.
The new serialization helper applies those values to locally transmitted gPTP,
sets minorSdoId=0, clears messageTypeSpecific, and clears reserved Announce
bytes (34..43 and 46), Pdelay_Req bytes (34..53), and two-step Sync bytes
(34..43). One-step Sync origin is preserved. Signaling header interval is127.
It preserves correction, identities, sequence and meaningful timestamp fields,
and leaves the standard PTP profile unchanged. It runs on copied Ethernet
wire buffers and on the Wi-Fi Announce/beacon FollowUp serialization paths.
The dedicated FTM relay template now also emits minor version1/control0,
with reserved header bytes zero. This is task-context preparation; the IRAM
transmit callback is unchanged. Upstream older minor versions remain accepted.

Native tests cover exact changed bytes and preservation, the actual Ethernet
serializer/caller template ownership, signed FTM correction and metadata,
Announce selection and existing callback wrap/expiry behavior. P4, endpoint C6
and responder C6 builds passed. Archives are `*-ftm-gptp-wire.bin/.elf`.
These images are not deployed yet. Final2020 verification and the remainder
of the flags/domain/interval/media state-machine audit remain open.

Header correction hardware verification:
All three images are now flashed; the endpoint also has a one-time diagnostic
after a successfully parsed, token-matched FTM vendor IE. It reported
`FTMWIRE,18,0,0,0,0,0,0`: version byte0x12, minorSdoId0, four zero
messageTypeSpecific bytes and control0, from received data. This verifies one
matched IE, not every received frame. The responder's time-critical callback
remains unchanged. Its application partition alone was written at0x10000,
preserving OTA metadata; the P4-assisted reset worked with Prog2 lacking EN.
Initial Ethernet capture independently validates all seven observed message
types (Sync, PdelayReq, PdelayResp, FollowUp, PdelayRespFollowUp, Announce,
Signaling) with zero header/reserved-field errors. Final capture counts and
clock regression follow in project.md. No final normative conformance claim.

AP association-state foundation:
A bounded 16-entry table now separates station MAC, association generation,
PTP neighbor identity and capability receipt. Active entries are never evicted
when full. Reassociation, including the same MAC, invalidates prior identity
and receipt; disconnect removes it; AP stop clears all peers. AP receive gates
require a known associated source MAC, and capability updates additionally
match the snapshotted association. Association events invalidate queued receive
and capability-transmit work conservatively across the physical AP port.
Initial station-list seeding runs outside locks and retries up to three times
if an event races the RPC; stale snapshots are never installed. Query failure
or sustained churn can leave pre-existing peers unknown until a later event;
a background reconciliation mechanism remains needed for that case.

ESP-Hosted event forwarding previously used strlen on a binary six-byte MAC.
The retained AP-event patch uses a bounded address check and preserves
zero-leading valid addresses. Native tests cover the installed expression,
per-station isolation/capacity/reconnect/expiry and the actual AP Signaling
gate, including stale association rejection. Both firmware builds pass.

This does not yet instantiate independent PortSync/MD state machines or
assign per-association transmit intervals/FTM state. Wireless asCapable remains
false pending media verification. The event-versus-parser final-check race
also remains; generation checks are not an atomic protocol transaction.

AP table hardware check: bridge logs now report a bound capability receipt
from the associated wireless endpoint. After restart, 79/79 source/path queries
returned MOTU and the complete three-clock path, with no timeouts. The unloaded
65-second capture reported no drops and no AAF traffic. This validates one
station's admission on hardware; multi-station isolation currently has native
test evidence only. No new scope measurement was made for this image.

Capability interval request and policy foundation, not integrated:
The Signaling codec now independently encodes/decodes subtype5, body length10,
with a 58-byte message. Existing capability subtype4 behavior is preserved.
Tests cover all256 signed interval encodings, special126/reset,127/stop,
-128/no-change, reserved-value TX rejection, bounds, duplicate TLVs, targets
and same-clock rejection. Reserved receive values remain available to policy
for explicit unsupported handling. The live daemon still ignores requests.

An isolated interval policy helper supports log intervals -3..24 plus the
special commands, and tracks nine accepted announcements before slowing down.
Failed or old-interval sends do not consume that count. Repeated identical
requests preserve progress; faster rates apply immediately. This helper is
not connected to the daemon or transport yet. It needs per-association TX
ownership, completion/lifecycle checks and scheduler integration before live
use. Hardware still sends at the initial one-second rate.

The public draft has an inverted slowdown comparison. IEEE's December2020
maintenance review explicitly identifies it as item0295 and illustrates the
corrected comparison. Source:
https://www.ieee802.org/1/files/public/docs2020/maint-congdon-AS2020-Cor1-items-1220-v01.pdf
Local copy: `build-ftm-discipline/as2020-cor1-maintenance-review.pdf`.
This resolves the direction of slowdown; it is not a substitute for the final
standard and published corrigendum. Remaining draft inconsistencies include
unsupported-rate mapping versus ignoring requests and the transition count's
exact diagram boundary. The helper follows the prose's nine-message behavior;
that decision still needs final-edition verification. Do not claim compliance.

2026-09-25 AP capability scheduling: per-association scheduler now reserves one
pending transport operation, carries a request token, and counts slowdown notices
only after transport acceptance. Copied worker completions contain MAC, association,
transport generation and token, never pointers into daemon state. A reconnect,
daemon restart, replacement request, duplicate completion or aged work cannot
advance the new request. Work and result queues are bounded, nonblocking, and
separate from Announce. AP transmission now uses targeted per-station work rather
than one shared fanout timer. STA still uses its fixed one-second timer.

Interval-request RX remains disabled pending the next integration test. The
scheduler helper and identity-bound request admission exist but are not called by
Signaling dispatch. Radio acceptance is not an over-air acknowledgement. The
final association/generation check and radio submission are not atomic with link
events. Distinct logical PortSync/MD instances and source port identities are still
unfinished. Do not infer multi-station conformance from independent TX cadence.

2026-09-25 12:42 UTC: AP interval-request RX is now implemented in source. Both
known TLVs are validated before either mutates state. Only an enabled, live AP
port and the currently bound source MAC/association/full PTP identity may change
its scheduler. Reserved/unsupported rates are ignored by policy. STA and wired
interval-request dispatch remain unfinished. Profile changes now retire transport
generations and reset per-peer schedules, preventing queued work/results from
surviving a profile transition. Native actual-dispatch and reset tests pass; both
builds pass. New interval-rx artifacts are NOT FLASHED. See
ftm-interval-hardware-test.md for the associated-station hardware procedure.

2026-09-25 pacing follow-up: the AP capability timer now preserves deadlines and
bounds the daemon poll wait by the earliest active association deadline. In the
associated-station repeat, all 56 fast-rate messages were received; measured TX
submission rate 7.999889 Hz, compared with approximately 6 Hz before this change.
TX gaps remained 119.7–130.4 ms and endpoint arrivals 69.9–180.1 ms. Exact media
conformance and permitted tolerances remain unproven. This is a capability-message
pacing result, not a new clock-accuracy measurement. STA and wired interval
negotiation, logical per-association PortSync/MD, and the previously listed vendor
and normative issues remain open.

2026-09-25 STA interval handling: the associated-AP neighbor now owns a capability
scheduler. Requests require the bound full PTP identity, BSSID and association.
Reconnects reset the negotiated rate, while identity replacement retires pending
work. STA capability frames now use copied targeted jobs with asynchronous
acceptance feedback and deadline-aware daemon waits, like AP stations. Profile
changes reset both directions. Native actual-dispatch and scheduler tests pass.
The wired port still uses its fixed initial interval; this change does not finish
wired interval negotiation or per-association PortSync/MD.

2026-09-25 wired interval handling is implemented and tested with controlled
bridge-unicast requests carrying the freshly observed peer PTP identity. All seven
requests were captured at ingress. Slowdown, rate increase, invalid-identity and
unsupported-rate rejection, stop and reset passed. This verifies the bridge's
handling, not that the MOTU emits these requests. Peer lifecycle and identity
changes reset the scheduler; temporary rate invalidity blocks requests without
silently discarding an existing negotiated rate. Send acceptance, not attempts,
advances the slowdown count. Final normative policy review remains open.

Latest independent loaded clock check, 13:17:16–13:18:20 UTC: 65/65 scope pairs
within one microsecond, no missing pairs; range -454.925 to +829.776 ns, median
+312.436 ns, absolute p95 767.272 ns. Common integer-second records matched 64/64
within the host-log window. This is output-edge alignment, with no probe correction,
not a direct measurement of MOTU internal absolute clock error or a universal bound.
Earlier runs include an excursion to 1.079 us. Loaded management had eight AVB-info
and eight path-query timeouts (122 valid source/path replies out of 130 rounds),
while FTM readiness remained up. DMA misses remain. No loss-free audio claim.

2026-09-25 14:22 update: Association identity/lifetime integration is now deployed
and validated; see ftm-association-media-audit.md and ftm-association-hardware-test.md.
A second managed Linux station received distinct Announce/Signaling port18 while
the ESP FTM endpoint stayed on port2. Wrong-local-target interval requests were
rejected; correctly targeted stop/reset operated independently. All29 independently
received wireless Announce frames carried the exact MOTU→bridge path, steps1 and
84-byte length. This supersedes the earlier missing wireless-path observation.
The concurrent scope window including second-peer removal had45/45 edges within
814ns. It does not prove two simultaneous FTM initiators or complete MD/PortSync.

The installed WIFI_EVENT_FTM_REQUEST exposes peer_mac, total frm_count (saturated
at255), burst_period, min_delta_ftm and accepted. It does not expose ASAP, burst
exponent, per-burst count or explicit requested-versus-granted values. Its own
header describes an asynchronous status notification. Before deriving media
qualification from this event, the missing grant semantics need supported evidence.
Do not equate accepted with a compliant grant or infer per-burst count from total.
The public issue's seven comments were re-read through GitHub's API; the latest
visible comment remained August25,2026. No newer public grant/raw-report/TM API
answer was found there. The vendor follow-up draft remains unsent.

## 2026-09-25 responder request observation

The deployed radio now samples WIFI_EVENT_FTM_REQUEST in event context, outside
capture_frame. It logs the first request, every 64th request and parameter changes.
Observed accepted=1, frm_count=8, burst_period=1 (100 ms), min_delta_ftm=20 (2 ms),
while the initiator requests period zero and logs a single ASAP burst of eight.
Requested-versus-granted semantics and period normalization remain vendor questions.
The event lacks ASAP, burst exponent, per-burst count and duration. Its current
association generation is contextual telemetry, not proof of the request's lifetime.
It does not qualify media or set asCapable.

The callback's 267 instruction words are identical before and after this logging
change. After recovery from a captured upstream timestamp anomaly and switch reboot,
45/45 scope pairs at 14:38:06.747..14:38:50.822 UTC were within one microsecond:
range -500.937..789.390 ns, median 116.534 ns, absolute p95 601.220 ns. No missing
pairs, empty records or rejected arming attempts; 3.2 ns sampling, no probe correction.
44/44 overlapping reported integer seconds matched without gaps or duplicates.
This is unloaded output-edge alignment, not absolute switch accuracy or conformance.
Evidence: build-ftm-discipline/request-observation-*.

A local, unsent vendor evidence bundle is available at
build-ftm-discipline/vendor-evidence-20260925.zip. Full media negotiation,
PortSync/MD roles, source handover and final normative verification remain open.

Synchronization-interval decoder update: subtype2 Message interval request is now
parsed separately from capability-interval subtype5. All three known TLV layouts
are checked before capability mutation, including mixed-message malformed/duplicate
cases. ASan/UBSan decoder tests, actual dispatch tests and both firmware builds pass.
This source change is not deployed. Sync/Announce scheduling policy is not connected;
the wireless initiator still uses fixed125ms cadence. Parsing alone does not satisfy
12.8 or implement SyncIntervalSetting/PortSync behavior.

## AP association synchronization stop candidate, 2026-09-25

The AP Signaling path applies subtype2 logTimeSyncInterval to the addressed,
identity-bound current association. Supported policy is default -3 and stop127;
126 restores default, -128 preserves current state, other optional rates are
ignored. This is separate from capability-interval subtype5. Announce and STA
synchronization scheduling are not implemented by this change.

Host snapshots now carry a per-peer stop flag and policy revision. The coordinated
radio map is FAM1 version2,292bytes:32-byte header,16x16-byte entries (MAC6,port2,
association4,policyRevision4), trailing32-bit stopped mask. Bits beyond count are
rejected. FAG1 envelope300bytes; old version/length rejected. A policy change
requires a snapshot prepared after activation, even if stop and reset are coalesced
before radio publication. Unchanged peers retain their snapshot activation.
Same-MAC rejoin or remote identity replacement resets stop policy. Lifecycle replay,
retirement and radio admission checks remain. Stop delivery is asynchronous through
host publication, not atomic with receive; actual latency remains to measure.

The callback declines gPTP Follow_Up emission for a stopped peer. This is NOT proof
that native FTM frames stop: the installed vendor header explicitly says the IE
is always sent at the fixed length even for nonzero callback return. The emitter
clears payload on rejection. Need a supported per-peer responder request/grant
control, or documented standards-compatible behavior; no false full-stop claim.

ASan/UBSan tests cover signed special/unsupported values, foreign identity/lifetime,
two peers, wire mask/codec, stop/reset, missed-stop publication and fresh-snapshot
resumption. Actual dispatch and callback blocks plus export, reconciliation,
Announce and capability scheduling regressions pass. All3firmware builds pass.
Candidate images host-sync-stop, coprocessor-sync-stop, endpoint-sync-stop bin/elf
and SHA256 manifest sync-stop-images.json are archived, NOT FLASHED. Hot callback
is786bytes in IRAM (previous766), same existing IRAM callees, map680bytes DRAM;
see sync-stop-callback-placement.json/.dis. No runtime latency or accuracy claim
for the candidate. Current deployed images and loggers remain unchanged.

Next coordinated deployment and finite per-peer stop/reset hardware test, then STA
initiation policy and remaining Announce/role/PortSync integration. Linux second
peer can test dispatch but not FTM; endpoint needs controlled subtype2 request
probe or authorized sender from its bound identity for actual exchange test.
Full gPTP goal active. Firmware generation mismatch means do not flash only one
side of the host/radio map change.

## 2026-09-25 15:02 UTC synchronization stop/reset deployed and measured

Added default-off ESP_PTP_SYNC_INTERVAL_PROBE (depends INTERVAL_PROBE), independent
subtype2 74-byte Ethernet encoder, finite sequence after30s binding: wrongidentity
stop127/4s, unsupported0/4s, validstop127/5s, unchanged-128/3s, reset126/15s,
default-3/3s, finalreset126. Both existing and new independent encoder tests pass.
Radio event-context FTMPOLICY logs applied port/lifetime/revision/stop changes;
no additional callback logging. Built/flashed host+radio+probeendpoint together.
Verified all device MACs and flash hashes. Prog2 NO EN boot strap procedure used.
No switch reset required; wired peer delay valid after startup.

Probe endpoint initially stayed in ROM after flash, fixed with default-reset
read-mac+hard-reset then logger. App boot14:56:30, sourcebound/probestart14:56:33,
READY14:56:42. Requests logged14:57:02 wrongidentity127,14:57:06 unsupported0,
14:57:11 valid127,14:57:16 -128,14:57:19 reset126,14:57:34 -3,14:57:36 reset126/DONE.
Radio FTMPOLICY stop port2/lifetime7/revision1 at14:57:11 and reset revision2 at
14:57:19. READY0/HOLD14:57:12, READY1 at14:57:22 (~3s afterreset, second-resolution
host timestamps). Guarded wrongidentity window23reports/22observations; unsupported
23/23; stopped24/0; unchanged16/0; recovered91/90. Native FTM reports continue while
gPTP Follow_Up data is suppressed. This demonstrates an application gate, NOT
native FTM stop or complete12.8 conformance. See sync-probe-result.json.

Scope sync-probe-scope.json/-summary:70acquisitions,54paired,all54within1us,
range-266.800..842.395ns,median223.026ns,absp95640.743ns;32ns samples at20us/div,
0empty/rejectedarming. First16 missingCH2 occurred14:56:44..59 BEFORE firstendpoint
pulse14:57:00. clock_scope_probe waits30000ms before enabling output; confirmed in
code+firstedge log. All54 acquisitions afterfirstpulse paired, including8s stop/
holdover/recovery. NOT70/70 claim. Integercomparison50/50common,nomissing/duplicate
14:57:01..51. Probe management test FAILED initialADPdiscovery whileendpointinROM;
no management-across-stop evidence. sync-probe-taps.pcapng all4taps,6107packets total,
zero reported drops (2052/890/1142/2023). Wireless subtype2 was observed through
endpointTX/radioapplication logs, not independently decoded on these wired taps.

Restored endpoint-sync-stop.bin (probeOFF) app-only0x10000, verifiedflash; extra
read-mac/default-reset/hard-reset got normalboot14:59:34. sdkconfig INTERVAL_PROBE
and SYNC_INTERVAL_PROBE disabled again; build-ftm-startup/endpoint still contains
probe-enabled build from test, so use archived image or rebuild before nextflash.
NormalREADY14:59:46. Final unloaded sync-normal-scope 15:00:23.877..15:00:57.914:
35/35paired+within1us,range-385.587..628.456ns,median252.255ns,absp95581.059ns,
0missing/empty/rejectedarming;3.2ns samples,no probe correction. Integer34/34matched.
Normal management14:59:54..15:01:08:236rounds,235bothOK,onepath timeout;all236AVBinfo
MOTU;235fullpathsMOTU+bridge+endpoint. Not flawless management/losslessaudio proof.
All finitejobs complete, scopeRUN, audioOFF;3serialloggers continue.

CURRENT DEPLOYED archived images:
P4 host-sync-probe.bin SHAfb58d1c5e87b04f7f0619716b712349d60911241e16ea97962d6ac2be8acc482,
loggerPID1144212/tool46542 host-sync-probe-live.log onACM3, boot2230896375.
Radio coprocessor-sync-probe.bin SHA3b4f997bfd2c9298911876e8663dfc6f76f770478e70af61587656abc906a928,
loggerPID1144202/tool30112 coprocessor-sync-probe-live.log onACM1,boot3560002073.
Endpoint endpoint-sync-stop.bin SHA7f61cac1d649faab09457820a7b1ed8f173971009bfa7c66ff810375ec5019ee,
loggerPID1145094/tool99752 endpoint-sync-normal-live.log onACM0. Probe firmware335f5a...
no longer deployed. Manifests sync-probe-images.json and sync-stop-images.json updated.
Deployed radio callback786bytesIRAM,map680bytesDRAM,sameexistingIRAMcallees;
sync-probe-callback-placement.json/.dis. No execution-time bound claimed.

Vendor unsentbundle refreshed with sync-stop-observation.json and perpeer responder
control question. Header contract says fixedIE is always sent even when declined;
no unsupported framecancellation assertion. FullTM/grant2or3/rawreportAPI/finaltext
blockers unchanged. NEXT STA initiation policy, Announce interval and actual roles/
PortSync behavior; current APgate only supports default-3/stop127/reset126/unchanged
and ignores optionalother sync rates. Peer-isolation nativeproof; this hardwaretest
singleactualFTMinitiator. Goalactive/notcomplete. Do notrepeat finishedprobe test
unless newcode or specificmissingacceptanceevidence warrants it.

## 2026-09-25 15:18 UTC STA initiation policy deployed

Previous turn made progress: AP timing gate, actual stop/reset and scope recovery.
This turn implemented STA policy in ptp_wifi_neighbor.h and actual subtype2 dispatch.
Shared ptp_sync_interval.h handles default -3/stop127/reset126/unchanged-128; optional
other values ignored. Peer/STA identity replacement resets policy and advances its
revision. New copied ptpd_wifi_sta_timing_snapshot API requires enabled/up gPTP STA,
associated and bound neighbor, returns BSSID/association/revision/stopped under lock.
FTM discipline scheduler polls stopped/unbound policy at50ms; event-loop start checks
again against actual AP; report admission requires unchanged association/revision and
BSSID and running policy. Coalesced stop/reset or peer replacement cannot admit an
old report. Already-started exchanges may finish; no atomic driver-handoff or immediate
cancellation guarantee. Legacy non-discipline path unchanged. Full roles remain open.

ASan/UBSan actual STA API/start/report extraction tests cover copied ownership, port/
profile guards, stop and coalesced reset, identity/reconnect rejection and lock balance.
Actual Signaling dispatch now tests STA subtype2 controls. AP gate/reconciliation/
registry/capability scheduler regressions pass. Both builds pass, diff --check clean.
Native outputs sta-policy-native-tests.log. No radio source changes this turn.

First bridge-originated diagnostic started before authoritative radio reconciliation:
SYNCTEST15:09:28,HOSTASSOC15:09:40,ABORT15:09:58 beforeanyTX. Preserved
sta-probe-aborted-result.json. Scope65/65within847ns was BASELINE ONLY, notstoptest;
management268rounds263bothOK,3AVBtimeouts2pathtimeouts. Corrected diagnostic AP start
requires coherent radio reconciliation when AP is via coprocessor; native AP retains
its existing lifecycle gate. Did not remove stale-generation safety. New probe build
host-sta-probe-reconciled (92ad38...) deployed for repeat, then restored normal.

REPEATED HARDWARE TEST: host ready/bound/reconciled before SYNCTEST15:12:59. TX15:13:29
wrongidentity127,15:13:33unsupported0,15:13:37stop127,15:13:42unchanged-128,
15:13:45reset126,15:14:00default-3,15:14:03reset126/DONE. Wrongidentity and unsupported
windows each23reports/22observations. Guardedstop15:13:39..41 andunchanged43..44:
ZERO starts/reports/observations; radioFTMTX counts2014valid/1275invalid constant
15:13:38..43. Recovery15:13:49..58 has76starts/75reports/75observations. READY0/HOLD
15:13:39,READY1 at15:13:47 (~2secafterreset, wall logssecondresolution). See
sta-probe-reconciled-result.json. No independent over-air frame capture claim.

Scope sta-probe-reconciled-scope 15:13:20.823..15:14:29.797:70/70paired+within1us,
range-714.941..819.770ns,median147.863ns,absp95714.941ns;0missing/empty/rejectedarming,
3.2ns sampling,no probe correction. Includes8s initiationstop and recovery. Integer
69/69common,no gaps/duplicates. Management279rounds277bothOK,1AVBtimeout1pathtimeout.
Guardedstop23/23bothOK,allMOTU+full3clockpath. No differentBTC amongreturnedvalues.
Both failuresoutsideguardedstop. All4tap capture completed; no inferred wirelessTLV
capture from wired taps. No switch reset needed for this turn.

RESTORED NORMAL DEPLOYMENT: bothprobeconfigsOFF. P4 host-sta-policy.bin SHA256
49a7a77fa5eb1bb7dd9811dc2a7286c10c5526603ed71849239215f2253ab202,
endpoint endpoint-sta-policy.bin SHA256
3c9c305a0e8f462a855d3d8622dc51a8768643cad84ca01483964325434ea60a.
Radio unchanged coprocessor-sync-probe.bin SHA3b4f997bfd2c9298911876e8663dfc6f76f770478e70af61587656abc906a928.
Manifests sta-policy-images.json markcurrentnormal,diagnosticmanifestsnotdeployed.
Host build directory still contains diagnostic image; MUST rebuild with restored
config or use archived normal image before flashing. Endpoint build normal.
P4 loggerPID1161752/tool94632 host-sta-normal-live.log onACM3,boot2893518195.
Radio loggerPID1144202/tool30112 coprocessor-sync-probe-live.log onACM1,
currentboot2321685807,epoch1 (same logfile spansseveral radioboots).
Endpoint loggerPID1158972/tool83215 endpoint-sta-policy-live.log onACM0,
currentREADY15:16:45 generation12 afterrestoration. Hardware IDs verified eachflash;
Prog2 NO EN; no radioflash thisturn. ScopeRUN/audioOFF. Allfinitejobscomplete.

Normal acceptance sta-normal-scope15:17:23.036..15:17:46.718:25/25paired+within1us,
range-376.046..616.390ns,median254.887ns,absp95538.903ns,0missing/empty/rejectedarming,
3.2nssampling,no probe correction. Normal management80/80bothOK,MOTU/fullpath.
New readable docs/ftm-current-status.md separates measured success from fullgoal;
project overview updated to user best-achievable target rather than stale proposed
confirmation. Next Announce interval policy, true perassociation PortSync/MD roles,
source/role handover and finaledition/vendorqualification. Latestloadedacceptance
stillpendingafterremainingintegration. Do notrepeatcompletedstop tests withoutnew
change orcoveragegap. Fullgoalactive, notcomplete.

## 2026-09-25 15:31 UTC AP Announce scheduling candidate

Previous goal turn was progress: STA initiation stop/reset deployed,70/70 scope
pairs within820ns across actualstop, normalrestore25/25within617ns. This turn
implemented per-AP-association Announce scheduling, NOT YET FLASHED.

esp_ptp/ptp_announce_schedule.h owns interval/deadline,policyrevision,pendingtoken,
per-logical-port sequence,source-information revision and slowdown count. Supported
rates are configured base log interval through24; faster validrequests normalize
to configuredbase (closest-supported longer), reservedvaluesignore,127stops,
126resets,-128unchanged. Currentbenchbase0(1s). Period calculations use microseconds,
roundup for sub-us values; no high-rate hardware support claim. On slowdown, header
immediatelyadvertisesnewinterval while3acceptedtransmissionsretainoldeffectiveperiod.
Failed submissions/stale completions do not decrement. Identicalrequest preserves
progress. Faster/reset/stopretirependingwork. Late completions cannot count toward
replacementpolicy. Count means transportacceptance, notradioACK/delivery.

ptp_wifi_peer_t nowownsannounce state. Identityreplacementretirepolicy,preserve
localsequence andserial; rejoinreinitializesviaexistingassociationlifecycle. The
host snapshotaddsannounce_revision; newcopied API ptpd_wifi_announce_begin/finish
validatesport/profile/AP/currentMAC+association underpeerlock. Worker checks copied
revision atconsumption, rewrites perpeer sourceport/sequence/logMessageInterval,
accountsactualAPIreturn. Expiry/linkgenerationchecksremain. No lockoverradioAPI;
finalcheck-to-driverhandoff notatomic andunavoidablependingframe notcancelled.

Worker-owned perphysicalport Announceinformationcache comparesfullbody44..end,
flags6..7,domain4,localclockidentity20..27, ignoringoriginTimestamp/sequence/interval.
ChangedBTC/quality/path/flags/localidentity bypasseslongperiod throughinformation
revision, withoutCRCcollisionrisk. Stopstilltakesprecedence. This enablespromptnew
information; it is notfullPortAnnounceTransmit/PortSync/role implementation.
General subtype2APdispatch appliesAnnounce independentlyofsync requestfield; unsupported
sync doesnotmaskvalidAnnounce. ExistingSTApolicy unchanged. STA/wiredAnnounceinterval
handling remainsoutsidecandidate. No newcallbackcalls or radiohotpathchanges.

Reference: localD8 10.3.10.2 explicitly3announceReceiptTimeout messagesatoldrate;
10.3.17 computeclosestlonger forunsupportedrates. BrowsedofficialIEEE maintenance
0295 https://www.ieee802.org/1/files/public/docs2020/maint-congdon-AS2020-Cor1-items-1220-v01.pdf
confirms correctedcomparison newinterval>old forAnnounce/Sync/Capabilityslowdown.
Finalnormativeedition remainsunverified. Do notuseinvertedD8diagramcomparison.

Tests ASan/UBSan test_announce_schedule.c:all256requestvalues,3acceptedoldratecount,
failures,identicalrequests,stop/reset/stale revisions,tokens,deadline/overflow/wrap,
configuredbase normalization,newsourceinterruptinglongperiod/pendingwork. Actual
queue/worker test coverscachechanges vsignoredtiming/seqfields,policyreject,sendfailure
accounting,twoidentities andexistingbounds/expiry. ActualsnapshotAPI testexercises
begin/finish,revisionexport andstalework. ActualSignalingdispatch testsindependent
sync/Announce fields,targetisolation,slower/stop/reset/closestbase. APregistry/reconcile,
FTMsyncgate,STAtiming andcapabilityschedulerregressionspass. Bothfirmwarebuildspass,
diff--checkclean. announce-policy-native-tests.log andbuild-announce-policy-*.log.

ARCHIVED NOTDEPLOYED host-announce-policy.bin SHA256
86b2d80acc49ad3e0ff1ce7e1ff1ea567f172943d7f5aed26c55228cc2aa939e;
endpoint-announce-policy.bin SHA256
26495e110744e7e21e017095117ca7031c603184fe12670cf789326833cd5505.
BothELFsarchived, announce-policy-images.json. Buildsnormal/probesOFF. Runninghardware
UNCHANGED: P449a7a77... host-sta-normal-live.log PID1161752/tool94632;
endpoint3c9c305... endpoint-sta-policy-live.log PID1158972/tool83215;
radio3b4f997... coprocessor-sync-probe-live.log PID1144202/tool30112. AudioOFF.
No pendingfinitejobs. CurrentradioFAM1v2wire292/FAG1300UNCHANGED;announce_revision
islocalhostmetadataonly andnotpublishedtoradio. Thus APcandidate canbe testedby
flashingP4only; endpoint/radio reflashing isnotnecessary for this change.

NEXT actualsecondLinuxassociation Announceintervaltest,usingexistingphy3 temporary
managedinterfaceasbefore. Extend independent send_peer_interval.py withsubtype2
Announce controls(sync/link=-128), capture actual first3oldrate/newheaderthen slower
cadence,wrongtargetstop,validstop/reset,andindependentlogicalsequence. Maintain
endpointFTM andscopeaccuracy throughsecondpeerchanges. Handle LinuxFTMlimitation:
it is onlya control/Announcepeer, notsecondFTMinitiator. FullPortSync/MDroles,source/
rolehandover,SDKgrant2or3/rawreport/TM/finalnormativegapsremain; goalactive.

## 2026-09-25 16:03 UTC, startup fix and loaded acceptance complete

Normalhost05711860... nowverified:prebootpeerpcap77Announce+77Capability,
bothsequence1..77,first15:56:10.364/10.135atHOSTASSOC15:56:10, no provisional
PTPbeforecoherence. Linuxport2,endpointport18. association-publish-result.jsonpass.
Scope15:56:20..15:57:19:60/60within1us,range-438.018..679.817ns,median156.210,
absp95647.950ns;0missing/empty/reject,3.2ns. Integerseconds59/59nogapsduplicates.
Management213/215bothOK,2pathtimeouts,allresponsesMOTU/full3clockpath.
Tempftmtest0disconnected/deleted; HOSTASSOCepoch3,count1at15:58:43.

Loadedacceptance association-loaded-* files: firstconnect15:59:22timeout,noreply
observedonendpoint-egresstap;cleanupdisconnectsuccessandtakerconnections0.
DoNOTclaimlostresponseasestablishedrootcause; commandvisibleonbridgeinboundbut
noendpointprocessingproof. Firstattemptcaptureassociation-publish-loaded.pcapng
alsooverlapssubsequentretry. Retrysucceeded16:00:25.244,90sfiniteaudiolease
finallydisconnect16:01:55.359. Subsequentget-tx-stateconfirmed0connections.

Actualscope16:00:36.928..16:01:45.856:70/70pairedwithin1us,range-390.481..745.961ns,
median238.712ns,absp95650.830ns,zero missing/empty/armingreject,3.2nssamples,
no probecorrection. Integerseconds70/70nogaps/duplicates. NoFTMREADYloss/HOLD.
275710AAFpacketswithcontiguoussequenceonbothenp1s0f1talkeroutandenp1s0f3bridgein
duringactualscopewindow(~4000pps). Fullcapture721282packets,oneflushedpacketf3;
no capturelossinferredintheguardedscopeAAFsequence. Management167/170pairs,
1AVBinfo+2pathtimeouts,allsuccessfulMOTU+3clockpath. Endpointplayoutgateepochs
repeatedlyadvance26..78,13decimatedreseedlogs, notclean audio/sample-clockproof.
Savedassociation-loaded-result.json,scope-summary,edge-seconds,management,pcap.
Plotannounce-source-loaded-clock-results.png compares4runswithoutpoolingimages.

CurrentP4loggerPID1190794/tool68211,host-association-publish-live.log,ACM3.
RadioPID1144202/tool30112coprocessor-sync-probe-live.log,ACM1;endpointPID1158972/
tool83215endpoint-sta-policy-live.log,ACM0. Radio3b4f997...endpoint3c9c305...
unchanged. Newendpointbuildarchivednotdeployed. Bothbuildspass, allfiniteprobes
OFF normalhost, no temporarymanagedinterface, originalmonitorch6, audioOFF,
scopeRUN, no finitejobs pending. No switchcycle. Fullgoalactive;clockdiscipline
demonstratedexperimentally, notfull802.1ASconformance. Docs/ftm-current-status.md
isreadablecurrentstatus; vendor/finalstandard/perassociationroleworkremain.

## 2026-09-25 16:12 UTC, profile reset and Announce expiry fixes deployed

Reviewfoundptp_reset_for_profile clearedcapabilityTXonly, leavingnewSyncstopand
Announcepolicyactive. Itnowclearscachedcapabilityreceipt, resetsAP+STAsyncpolicy
withnonzerorevisionadvance, resetsAPAnnouncepolicyretainingserial+sequenceand
advancingrevision. Helpersreuseexistingidentityreplacementsemantics. Oldtokens
andoldcopiedpolicy revisionscannotcomplete/admitnewwork. Physicalassociation
andboundidentityarepreserved. NoFTMcallback changes.

Announce receipttimeout hadsupportedonlylog-8..8withfallback3seconds. Itnow
supports-24..24,matchingAPpolicy. Compute3intervalsdirectlyin64bitns,ceilfor
negativepowers;othersretainconfiguredfallback. Nativeactualsourcevaliditytest
covers49rates,expiryboundary,negativeage,unqualifiedwiredsource,Syncnotrenewing
expiredAnnounce,andallotherint8values. Nativeactualreset/scheduler/API/STA/
SignalingandAnnouncescheduletests passASan/UBSan,includingwrap/pendingtokens.
profile-reset-native-tests.log; bothfirmwarebuildspass;diff--checkclean.

FlashedverifiedP4ACM3MAC80:f1:b2:d2:ca:a9 app-only0x10000:
host-profile-reset.binSHA423f7a63c41d3eb006724e88a71147bd877ea9368e0742dfc659b03ea55d7b35
ELFbe50f7fc45e57891a70844c4ebf315d20320c8cd4b5ac16cbfc79bf05e7d7f08.
FlashedverifiedendpointC6ACM0MACfc:01:2c:fd:fe:80 app-only0x10000:
endpoint-profile-reset.binSHA35f1c17a460ebccaa111c23af5babc031d3e8553febcf4d2c7ab95f0b5e673dd
ELF123a113b6c769c5f9cad74e7f31e964724292156bd05b2f5d45a7e6aec490716.
Explicitendpointread-mac/default-reset/hard-resetafterflashthenloggerbootsapp.
Normalfault/loss/intervalinjectionOFF; read-onlyCORE_AUDITremainsonP4asitwas
previously. Earlier'allfiniteprobesOFF'notesreferfault/intervalinjections, not
thisread-onlystartupcoreaudit. RadioUNCHANGEDcoprocessor-sync-probe.bin3b4f997...
profile-reset-images.jsoncurrent;association-publishandsta-policymanifestsnow
notdeployed. AllarchivedbinsandELFsretained.

EndpointselectedMOTU+bridge16:10:25,READY1at16:10:29gen3.
Finalscope16:10:44..16:11:18:35/35pairedwithin1us,range-534.547..646.545ns,
median225.938ns,absp95646.447ns;zero missing/empty/rejectedarming,3.2ns sampling,
no probecorrection. Integer35/35secondsnogaps/duplicates. Management95/95
bothOK,zero timeouts,allMOTUBTC+full3clockpath. profile-reset-{scope-summary,
management-summary,edge-seconds}.json. ThisishardwareNORMALacquisitionregression,
notliveprofiletransitionproof; nativeactualresetcodecoverspolicytransition.
Earlierloaded70/70<=746ns wasprevioushost/endpointimages, doNOTpoolconfigs.

CURRENTloggerPID1194960/tool36925host-profile-reset-live.log ACM3;
endpointPID1194950/tool19729endpoint-profile-reset-live.log ACM0;
radioPID1144202/tool30112coprocessor-sync-probe-live.log ACM1(spansboots).
ScopeRUN,audioOFF,notempmanagedinterface,originalmonitorch6. Allfinitejobsdone.
No commits/pushes, noexternalmessage, noswitchcycle. ActivegoalNOTcomplete.
NexttrueperassociationPortSync/MDroles andsource/rolehandoverintegration,
STA/wiredAnnouncepolicy,mediagrantqualification/finalstandard/vendorAPIs.

## 2026-09-25 16:32 UTC, normal Announce qualification deployment verified

PostswitchrecoveryWITHOUTfirmwarechange:55matchedPdelayexchangesMOTUsource0003
reportT3-T2min30184/max34880/median32488ns, bridgeinboundnowenp1s0f3(asverified
byrequesteridentity), differenttapmappingafterlinkbounce. JSONannounce-normal-
pdelay-recovered.jsonandpcap. Wiredpeermeasured~435nsvalid. Shellyauthorized
5secondcyclewasneededonce16:29:29afterindependentfaultcapture, notblindreset.

Normalpostrecoveryscope16:30:33..16:31:03:30/30paired,29/30within1us;range
-320.437..1052.264ns,median106.645ns,absp95865.685ns;no missing/empty/armingreject,
3.2ns,no probecorrection. Outlierindex17at16:30:50.929retained,notrerununtilgreen.
Integerseconds31/31nogapsduplicates. Management95/95bothOK,zero timeouts,
MOTU+full3clockpath. announce-qualification-recovered-{scope-summary,management-
summary,edge-seconds}.json. Initialfailednormalrunhas30/30missingpairs, retained
announce-qualification-normal-scope-summary.json. ExplicitlyNOTsubusboundproof.

CurrentNORMALP4host-announce-qualification.bina2a5c88433643821d0969175191c4e0fcf23d015e75112fd3bb024a112ee0839
ELF0fe9cb181bdd5d48a67fcf1a60610d52cfc8f98abfe1bba372f3a05150fb4a28.
Endpoint99ded9bc8de4c04ef92ba1b81f4ad931640cfa4d3e3186e27eb3476407554974
ELF40512c66649397aecb901efc4234bcfb2c3516549d9d4b620b12e459da07f597.
Manifestannounce-qualification-images.jsoncurrenttrue,profile-reset/diagnosticfalse.
P4loggerPID1205678/tool11231host-announce-qualification-live.logACM3;
endpointPID1204626/tool16483endpoint-announce-qualification-live.logACM0;
radioPID1144202/tool30112coprocessor-sync-probe-live.logACM1. Radioimageunchanged
3b4f997...,currentboot2287432047. Hostboot341254363. EndpointREADY1gen6at16:29:50.
Allfinitejobscomplete,scopeRUN,audioOFF,notempmanagedinterface,originalmonitorch6.
HostbuilddirectorySTILLdiagnostic90319696althoughsdkconfigprobeOFF. MUSTuse
archivednormala2a5orrebuildunderrestoredconfigbeforeflash. Endpointbuildnormal99ded.
No commits/pushes/externalmessages. Goalactive,previousgoalturnmadeprogress.

Nextroleintegrationfinding: ptp.cownidentityinitializationusesCONFIG_ESP_PTP_SERVER
ORCONFIG_ESP_PTP_GPTP_PROFILE, sobenchpriority1=248/class248declaresrooteligible
evenwithSERVERoff. APAnnourcepublishesownidentitywhenupstreamselectionlost,
butclock_probeFTMtransferonlyvalidwithupstreamtimingsnapshot. Localrootclock
originationandportroledecisionsarenotcoherent. DoNOTclaimfullPortSync/MD; need
implementlocalclocksource/role/selected-sourcehandoverconsistentlyratherthan
silentlynarrowrootcapabilitytohidegap. OptionalPathTracefixnowhardwaretested;
16upstream-pathcapacityremainsresourceboundnotarbitrarytopologycompliance.
Finalstandard/vendor2or3framegrants/rawfailureAPI/TM/perpeermediacontrolstillopen.


## 2026-09-25 16:48 UTC, local hardware-root FTM origination

Implemented a separate local-source snapshot and downstream source reader in
esp_ptp. The received-observation API retains its previous meaning. The daemon
publishes from its running hardware clock only for a selected eligible local
root; it retains oscillator trim and uses zero upstream delay/correction. Both
snapshots are retired on source invalidation. Sync-only loss cannot enable local
fallback while the upstream Announce remains selected. The FTM host mapper and
publisher use the new reader; radio callback and radio firmware are unchanged.
The timing diagnostic label is now TIMINGSOURCE (analyzer accepts old UPSTREAM).

Correction to the earlier role review: wired Sync origination was already under
SERVER OR GPTP_PROFILE, so it did not require enabling SERVER in this gPTP build.
The missing origination was the host-to-radio timing snapshot.

Native actual-code tests pass for local timestamps/identity, retained trim,
upstream/local separation, 500-ms freshness, handover, eligibility and clock-read
failure, plus existing timing admission, expiry and Announce tests. Both targets
build. tools/ptp_status/test_local_source.py and local-source-native-tests.log.
Endpoint-local-source was built but is NOT deployed; unchanged endpoint remains
99ded9bc8de4c04ef92ba1b81f4ad931640cfa4d3e3186e27eb3476407554974.

Extended the finite source-loss diagnostic with an 8..60-second Announce-loss
setting (default 8); tested precise boundaries at 8 and 24 seconds. Hardware test
used 24 seconds, then 12-second recovery and four-second Sync loss. Diagnostic
image 16fd43f47b1b56761fd7a2dbc313d2cbf92912721ec4d6774bdbdf79874944c0 is retired.
24 Announce and 64 Sync/FU messages discarded; taps independently saw upstream
traffic. Local selection at 16:42:53, READY1 at 16:42:58; upstream resumed 16:43:14,
READY1 16:43:22. Sync-loss READY0 16:43:28, READY1 16:43:31. Times have one-second
resolution. Reacquisition gaps mean this is not hitless handover.

local-source-probe-result.json passes. All 316 management pairs succeeded with
expected BTC/path in guarded windows. Initial discovery failed during startup;
retry started at 16:42:50, after suppression began but before Announce expired.
Initial analysis expected pre-suppression queries and failed missing baseline;
retained local-source-probe-result-initial.json. Corrected pre-expiry window has
seven good MOTU queries, independent timing snapshots and a margin before local
selection at 16:42:53. No measurements removed.

All 85 scope pairs including transitions were within 1 us: -671.339..700.275 ns,
median151.030 ns, absolute p95 646.919 ns. Zero missing/empty/rejected arming;
85 matching integer seconds, no gaps/duplicates. Settled local-root 13 pairs
-51.383..510.962 ns. Scope measures bridge-to-endpoint output alignment, not an
independent absolute MOTU clock. 3.2-ns samples, no probe correction. Earlier
1.052-us outlier remains valid evidence against claiming a guaranteed sub-us bound.

Restored NORMAL host-local-source.bin SHA
87f814f3dd3013cf5674b9e42f2efe40d236b890327c415f1dc7db35878b5e85,
ELF611df7c24bdbfbda827d3b1806b49f0c09db406cdf7472034592afee3c2e928b.
Build directory and sdkconfig now match NORMAL (both source-loss/path probes OFF).
local-source-images.json marks normal host deployed, diagnostic/endpoint build not
deployed. Host ACM3 verified MAC80:f1:b2:d2:ca:a9 before each flash. Current logger
PID1227725/tool94371, host-local-source-live.log, boot3567088409. Endpoint unchanged
ACM0 PID1204626/tool16483 endpoint-announce-qualification-live.log, READY1 generation12
at16:46:32. Radio unchanged ACM1 PID1144202/tool30112 coprocessor-sync-probe-live.log,
image3b4f997bfd2c9298911876e8663dfc6f76f770478e70af61587656abc906a928,
current radio boot258794441. No EN on Prog2, user override still applies.

Normal verification 16:46:52..16:47:26:35/35 paired and within1us,
-302.664..930.453ns,median207.501ns,absolute p95779.103ns;35 matching integer seconds,
no missing/empty/armingreject. Management143/143 success, all MOTU/full3-clockpath.
Artifacts local-source-normal-{scope-summary,management-summary,edge-seconds}.json.
Tap mapping independently verified by requester identity, bridge inbound enp1s0f2
(76 responses); local-source-normal-tap-map.json. No switch reboot needed this turn.
All finite jobs completed, scope RUN, audio OFF, no temporary managed interface.

Next: complete local ClockSource time-base change metadata and consistent port
roles. Current local FU uses existing zero-initialized information TLV template;
this is NOT complete ClockSourceTime behavior across repeated roles. Root-ineligible
(priority255) Announce/Sync suppression also remains: new snapshot rejects it but
older generic transmit paths can still advertise own clock. Full per-port BTCA,
wireless qualification, final-standard review and vendor two/three-frame grants,
supported failure timestamp API, legacy TM/per-peer controls remain open.
Read docs/ftm-local-source-handover.md and docs/ftm-current-status.md. No commits,
pushes or external messages. Goal remains active; this turn made concrete progress.


## 2026-09-25 17:03 UTC, root presence and queued Announce ownership

Current source and NORMAL images add eligibility checks for local wired Sync,
legacy wireless Sync egress, incoming Sync/FU, FTM source observation and status
validity. A selected priority255 vector can participate in topology selection but
cannot refresh timing or report a valid received clock. AP Announce queued work
captures ptpd_timing_generation and rechecks it before dispatch and each peer.
Source invalidation retires queued old-body work, independently of link/peer
association generations. No radio ISR/callback changes. A frame already handed
to the driver may finish; no atomic driver cancellation claim.

Important correction to prior notes: DO NOT suppress priority255 Announce.
The early local edit did this incorrectly, was reviewed/corrected BEFORE any
hardware deployment, and its archived pre-review builds are NOT deployable.
D8 Figure10-18 preserves Announce participation; SiteSyncSync gates timing with
gmPresent. IEEE maintenance request159 explicitly confirms both Announce
participation and relaying eligibility for a root-ineligible bridge:
https://www.ieee802.org/1/files/public/maint/requests/maint_0159.pdf
https://grouper.ieee.org/groups/802/1/files/public/maint/new-requests/287/requests/13.html
Final target-edition validation still pending. No reference implementation code copied.

Native ASan/UBSan tests pass: actual periodic egress at all256priorities and both
local/selected roles; priority255 selected vector suppression; FTM observation
admission at all256priorities (rejection cannot refresh receipt or generation);
status selected-but-invalid semantics; actual AP queue stale source generation
before dispatch and between peers; prior local-source, wired gate and Announce
relay cases. root-egress-native-tests.log. Both normal builds pass.

Hardware priority255 diagnostic used finite24sAnnounce discard,12srecovery,4sSync
loss. Image5752cc7495c52e5a93cde431fae7f04bc5e2d3eb61b35f051659b6bbfa052133,
ELF9e79738f098aa6d611905d14f4db364b06333a9572676a0e90ef7ddb34be48e1, now retired.
Phases16:55:48,16:56:18,16:56:42,16:56:54,16:56:58UTC;24Announce+64SyncFUdiscarded.
Guardedno-root16:56:23..16:56:41 captured18Announcepriority255+18capability messages
on BOTHwired and managedpeerlinks, zero wiredSync/FU. Radio15FTMTXsamples valid
counter1175unchanged, invalidcounter489to1530. Host15invalid timing snapshots.
Management269/269success;13nogm-windowqueriesreportedendpointownidentity (endpoint
priority248beatsbridge255),101restored-windowqueriesMOTU. No claim that endpoint's
local software-clock origination/full roles are implemented.

root-ineligible-result.json no_root_behavior_pass=true, functional_pass=false:
one missing captured Announce seq4 at16:56:00, between seq3at16:55:59.159663 and
seq5at16:56:01.159514. Same logicalsource80f1b2fffed2caa90012 andMOTUBTC;beforeoutages.
93capturedAnnounce seq1..94 except4, all subsequent contiguous. Cannot identify
sender/transport/capture loss from this capture; retained failure, not rerun until
it disappeared. Linuxpeercontrolonly, notsecondFTMinitiator. Capturehad0reported
dumpcapdrops. Tapsindependentlyidentifiedbridgeoutboundenp1s0f3,inboundenp1s0f2.
A tshark field query used unavailable ptp.v2.messageid and produced empty TSV;
actual analysis uses decoded raw PTP bytes from tshark JSON and is unaffected.

Restored NORMALbothimages afterverifiedMACs: bridgeACM3,endpointACM0.
Hostroot-egress.bin a89900faf3778410cdd0be7195dc223f218b91993db7d9411a488db8f30cbd9f
ELFb721651c4520aa6cbbc568f0456f3af02b75b190aac32fcafb1451982166125b.
Endpointroot-egress.bin2425aa54e3e9915dc210931de7159e9fb4ef8c976c7e743066c94b3aaf8090f7
ELF4b97ce2290597041035dda879f727bb3cd55ffae9d86d8536a5421a3cbafffb1.
Manifestroot-egress-images.json marksbothnormaldeployed,diagnosticfalse;
announce-qualification/local-source manifests allnotdeployed. Builddirectories
matchnormal configs,hostpriority248,source-loss/pathprobesOFF. Pre-review archives
containrejectedbehavior and MUSTNOTflash. Radioimageunchanged3b4f997bfd2c9298911876e8663dfc6f76f770478e70af61587656abc906a928.

Currentloggers: P4PID1244913/tool16496 host-root-egress-live.logACM3,
boot2223441087; endpointPID1244905/tool51828 endpoint-root-egress-live.logACM0,
READY1generation3at17:01:00; radioPID1144202/tool30112coprocessor-sync-probe-live.logACM1,
currentboot1220570579. UseroverrideProg2NOENremains. Allfinitejobscompleted;
scopeRUN,audioOFF,temporaryftmtest0disconnected/deleted,originalmonitorunchanged.
No switch reboot needed. No commits/pushes/externalmessages.

Normal acceptance17:01:20.987..17:01:54.947:35/35scopepairswithin1us,
-156.219..522.649ns,median249.230ns,absolute p95521.914ns. No missing/empty/arming
reject;3.2nssamples,no probe correction. Management143/143successallMOTU/full3clock
path. root-egress-normal-{scope-summary,management-summary,edge-seconds}.json.
Tapmapreverifiedbridgeinboundenp1s0f2,76matchedPdelayresponses. Earlier1.052us
outlierremains;latestshortcaptureisnotaguaranteedsubusbound.

Next substantial protocol correction: current Sync-only loss preserves selected
MOTUwhileclearingFTMreadiness. D8 sections10.3.12and10.3.13 (textaround10834..11099)
requireSync receipt timeout, whengmPresenttrue, toageAnnounceinformationandfeed
source/role selection. EarlierfiniteSync-loss tests provedimplementedbehavior,
NOTcompliance. NeedintegratePortAnnounceInformation/PortStateSelectiontimers,
includingacquisition, repeatedAnnounce vsactualSync renewal, independentAnnounce
expiry, andretireselectedtiming/queuedworkconsistently. Donotsimplytreatlatest
AnnounceasrenewingSyncorclaimreadinessalonecompletesselection. LocalClockSource
time-base metadataacrossrepeatedroles andfullper-portBTCA/STA-source rolesremain.
Finalstandard/vendor2or3frameASAPgrant/rawfailureAPI/TM/perpeermediacontrolstillopen.
Goalactive;turnmadeconcretecode,protocol-reviewandhardwareprogress.


## 2026-09-25 17:25 UTC, Sync receipt expiry integrated and exercised

Added esp_ptp/ptp_sync_receipt.h with daemon-owned monotonic receipt state,
three-interval expiry, safe elapsed arithmetic, bounded exponent conversion and
poll-deadline limiting. Announce acquisition/vector change seeds the timer;
repeated identical priority vectors do not renew it. Exact Announce expiry now
uses >=. The gPTP validity path independently checks Announce and Sync expiry;
priority255 topology information is exempt from the Sync-present requirement.
Legacy non-gPTP validity keeps its previous behavior. This remains the existing
bootstrap-port selection implementation, NOT complete per-port state machines.

Wired two-step receipt renews only after a matching complete usable Follow_Up
and successful clock update. Malformed information TLV and invalid Sync interval
are rejected before changing the clock. Large accepted clock steps still renew
receipt even when they retire the mapping generation. FTM observations now carry
log_interval and received_us through the local queue into ptpd_ftm_source_observed;
expired, future and out-of-order observations cannot renew the timer or obtain a
new discipline generation. Internal API signature changed in ptp_ftm_clock.h and
its sole application caller. No RPC/wire layout or radio callback change.

Daemon processes FTM observations before source-expiry evaluation, invalidates
selected timing before periodic publication, and limits poll wait by the receipt
deadline. SYNCTIMEOUT logs contain now_us, receipt_us, interval_us. Native tests
cover actual Sync/Follow_Up handlers, source validity, Announce refresh/vector
changes, FTM admission, exact boundaries, stale queue age, timer overflow and
wait deadlines. ASan/UBSan tests and both builds pass; sync-receipt-native-tests.log.
MOTU wire capture showed1218Sync messages all log interval-3 (125ms); default
three-interval receipt timeout is375ms. Based on available D8 sections10.2.8,
10.3.12/13, not a final-edition conformance claim.

Initial normal b801815...host/7788dd6...endpoint before poll-deadline refinement
had40/40scopepairswithin1us (-360.993..699.958ns,median240.155,absp95618.520),
159/159managementpairsallMOTU,41matchingintegerseconds. Three endpoint startup
expirations preceded map availability; no settled expiry. Baseline artifacts
sync-receipt-baseline-*. These images are now NOT deployed.

Finite diagnostic host46a9e1709995e93fbfab3f93253823c555cf6bd027f919a17d72099b2d5fd697
ELFf7668759f34fde264b5bdeee845bcbdac2ca2f9d3844b13d4304a43e1e379133,
usedfinalnormalendpoint367bf3... . Source-loss phases17:17:31,17:18:01,17:18:25,
17:18:37,17:18:41UTC:24Announce and63Sync/FUdiscarded. Independent tap verified
32Sync,32FU,4Announce during the coarse four-second Sync-drop window. Inboundtap
wasenp1s0f3,identifiedbyPdelayrequester. Bridge expires at375039,376979,376941,
376959us after receipt/acquisition; each timerinterval375000us. RepeatedAnnounce
initiatesnewacquisitionafteraging but cannotrenew anexistingtimingreceipt.
WireAnnounce root changes MOTU->bridge at17:18:37.468832, then alternates on new
Announce/acquisition and expiry, returning MOTU17:18:41.218130. Logicalsource
identitystaysfixed;113Announce sequencescontiguous. This directly fixes the
previous behavior of indefinitely preserving selectedMOTU on Sync-onlyloss.

Scope90/90paired,no missing/empty/armingreject,88/90within1us,
-443.429..1058.322ns,median220.539ns,absp95878.716ns. Outliers:
index26,17:18:24.129485,+1023.063ns (end of local-root window);
index43,17:18:41.141816,+1058.322ns (Sync restoration boundary).
Localrootsteady13/13<=878.716ns;Syncoutage4/4<=914.533ns;finalrecovery30/30<=908.626ns.
92matchingintegerseconds,nogapsduplicates. Scope3.2nssamples,no probecorrection;
this is bridge/endpoint edgealignment, not independent absoluteMOTUclockaccuracy.

Management316/317pairscomplete. AVB_INFO timeout17:18:32.996882 (pathquerysucceeded,
fullMOTUpath). Retained all measurements. sync-receipt-probe-result.json has
receipt_behavior_pass=true, functional_pass=false because not all management
pairs completed. Initial analyzer classified protocol-only checks as functional;
it now explicitly includes management completion in functional_pass. No data
removed and no rerun to hide the outliers/timeout. Linuxpeercontrolonly,notFTM
initiator. Temporaryftmtest0disconnected/deletedaftercapture.

Restored NORMALfinalhost-sync-receipt-deadline.bin
36f32fe63e96fa13e271bd1e8020c1c5124f457c23281bb8fe049b88dde44e91
ELFff71d6466f2603509b06542e6806342e300be37239a1080c60bb82a5508ac21d.
Endpoint-sync-receipt-deadline.bin
367bf3bb09b6ec0281c6210d54c1d22b10202fe115f8e5430d28f5ca2f01b651
ELF39f1f70c41272754dc4e6563b8649d212894a1b9db9d9c4c108a4d211677651c.
Bothcurrentnormalbuilddirsandconfigs match,hostpriority248,source-loss/pathprobesOFF.
Manifest sync-receipt-images.json marks these two images deployed, all earlier
baseline/diagnostic variants false. root-egress manifest allfalse. Radioimage
unchanged3b4f997bfd2c9298911876e8663dfc6f76f770478e70af61587656abc906a928.

Currentloggers: hostACM3PID1265776/tool46316 host-sync-receipt-deadline-live.log,
boot1559288489; endpointACM0PID1264687/tool54638 endpoint-sync-receipt-deadline-live.log
(spansdiagnosticandnormalrestoration),READY1gen49at17:22:50; radioACM1PID1144202/
tool30112coprocessor-sync-probe-live.log,currentboot247674623. VerifyUSBMACsagain
beforefutureflashes. Prog2 hasNOEN,useroverride. No switch reboot thisturn.
Allfinitejobscompleted,scopeRUN,audioOFF,notemporarymanagedinterface.

Finalnormalacceptance17:23:12.074..17:23:46.091:35/35within1us,
-429.225..758.778ns,median278.802ns,absp95658.250ns;no missing/empty/armingreject.
36matchingintegerseconds. Management143/143allMOTU/full3clockpath. Tapinbound
reverifiedenp1s0f3with76Pdelayresponses. Artifacts sync-receipt-normal-*. No settled
SYNCTIMEOUTafter17:22:50. Initial acquisition on each radio restart still expires
several times before mapping is ready; not suppressed by extending deadlines.

Next useful operational cleanup found: ftm_clock_probe.c::probe_task explicitly
sleeps15000ms before capture/association setup, then CONFIG_FTM_CLOCK_PROBE_CORE_AUDIT
runs another~5s of diagnostic reads. Both are cold-path test artifacts, but cause
initial Announce to precede usable mapping and trigger acquisition churn. Replace
fixed startup sleep with readiness-based initialization and disable optional audit
in operationalconfigs, with startup/normal regression. Do not merely increase
Sync timeouts to mask unavailable timing. Complete per-portAnnounce/PortSync/MD
state machines, stop/reset interval interactions, local ClockSource time-base
change metadata, loaded validation of latestimages, and actual simultaneousFTM
initiators remain open. Finalstandard and vendorgrant/rawfailure/TM APIs remain
blockers to conformance, not proof of hardware incapability. Goalactive;thisturn
made code, protocol and hardware progress. No commits/pushes/externalmessages.

## 2026-09-25 final-standard verification

Checked against `Documents/Standards/8021AS-2020.pdf` and the 2021 corrigendum.
Fixed in the working tree, with native tests updated: VendorSpecific IE OUI
00-80-C2 (12.5.1.4.1 b), gPTP-capable TLV and interval request tlvType 0x8000
(10.6.4.4.2, 10.6.4.5.2), closest-longer mapping for unsupported faster
gPTP-capable rates (10.4.3.2.2), per-port Follow_Up sequenceId with dialog-token
pairing (10.5.7, 11.4.2.8), and the 12.3/12.4 asCapable determination on the STA
port. The Cor 1 slowdown direction and nine/three-message counts used here match
the corrigendum. Bench senders and analyzers under `tools/` follow the new TLV
types; the earlier "unsupported rate rejected" stage of the interval probe is now
"faster request normalized to the fastest supported rate", which produces the
same advertised interval. Both ends of the wireless link must run the updated
images together. SDK blockers are unchanged: no three/two-frame ASAP burst grant,
no burst duration or Min Delta FTM control (Table 12-3), no supported access to
discarded reports, no legacy TM service, and no per-station Extended Capabilities
on the AP side.
