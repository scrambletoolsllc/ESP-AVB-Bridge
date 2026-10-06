# Per-association media-state audit

Current status, 2026-09-25: coordinated identity/lifetime integration is deployed.
Announce, Signaling and FTM Follow_Up use the same association identity. A second
Linux station demonstrated distinct port identity and directed capability-interval
request isolation while the endpoint retained sub-microsecond edge alignment.
The second station was not an FTM initiator; concurrent FTM exchanges remain untested.
Full media qualification and PortSync/MD roles remain incomplete. The sections below
record implementation history; earlier statements of missing integration are
superseded by the coordinated runtime section and ftm-association-hardware-test.md.

The current bench has demonstrated clock alignment for one wireless association.
The public D8 text, clause 12.1.2, describes a separate PortSync and MD instance for
each association. Final-edition normative review remains necessary. Independent
capability timers alone do not provide these instances.

## Current code evidence

- `esp_ptp/ptp_wifi_peers.h` owns association lifetime, remote identity, capability
  receipt state and capability transmission schedule separately for each station.
- `esp_ptp/ptp.c` still derives AP Signaling source port from physical `index + 1`.
  Timing-message processing explicitly excludes ingress ports other than zero.
- `esp_ptp/ptp_wifi.c` still shares the physical-port Announce publication across
  AP stations. It does not carry a per-association logical source-port identity.
- `components/ftm_clock_probe/ftm_clock_probe.c::publish_transfer` fixes the
  Follow_Up source port to 2. `receive_transfer` creates common timing snapshots.
- `capture_frame` receives the initiator MAC, explicitly ignores it, and selects
  a common snapshot only by timestamp and expiry.
- The patched `esp_wifi_ftm_resp_vendor_ie_cb_t` in the local SDK supplies the
  initiator MAC. Peer selection is therefore possible locally with this patch.
  This does not resolve the separate TM, burst-grant or raw-report API questions.
- `ftm_transfer_t` is a versioned 168-byte transport record. Both the custom-data
  multiplexer and receiver check its exact size. Updating only the producer would
  silently fail dispatch; host and coprocessor must be updated together.

## Required coordinated work

1. Represent each AP association's logical PortSync/MD identity and lifecycle,
   keeping logical identities distinct from physical transport indices. Establish
   a collision-free port-number allocation and check it against the target text.
2. Select the corresponding identity for outgoing Announce and Signaling, and
   validate incoming directed Signaling against that association's local identity.
   A station must bind the same peer identity it later sees in its FTM Follow_Up.
3. Publish association metadata with clock snapshots through the existing custom
   channel. Preserve the callback-slot limit, version checks, host/radio boot IDs,
   and source-generation invalidation. Include association lifetime and freshness;
   a MAC alone cannot distinguish a reconnect to the same station.
4. In the radio callback, perform only bounded IRAM/DRAM lookup and encoding.
   Reject unknown, expired or retired association work. Do not add allocations,
   Wi-Fi API calls, logging, unbounded loops or 64-bit division. Ensure the chosen
   association lifetime covers the timestamp referred to by the Follow_Up token.
5. Add media qualification/negotiation state and role/PortSync ownership. A MAC
   lookup and rewritten source port are necessary plumbing, not complete MD state.
   Keep Wi-Fi asCapable false until its actual media requirements are satisfied.
6. Test two concurrent associations, removal, same-MAC reconnect, old queued
   publications, source changes, and consistent source identity across message
   types. Single-station bench evidence cannot establish multi-station isolation.
   Recheck the callback's code placement and measured clock alignment under load.

Do not partially deploy changed Announce identities while the responder still
emits port 2, or claim that a peer table by itself completes clause 12.

## Association metadata support implemented, not connected to the live path

`components/ftm_clock_probe/ftm_association.h` defines a separate 224-byte,
versioned, little-endian record for up to 16 MAC/port/lifetime entries. It carries
host/radio boot ownership, publication serial and the local clock identity.
Encoding is independent of C struct padding. Decoding validates the whole record
before changing output, rejects duplicate MACs or ports and nonzero unused bytes.
This record is not yet accepted by the existing custom-data multiplexer.

The isolated radio-side state rejects foreign boot ownership, replay and backwards
local time. It expires after one second without a refresh. New lifetime, changed
port or clock identity, and recovery after expiry require a clock snapshot prepared
strictly after activation. Unchanged timely refreshes preserve that boundary.
Local retirement survives same-lifetime refreshes, including expiry recovery;
AP-stop retirement retains replay history. A newer association can reactivate it.

The selector uses bounded byte comparisons, no allocation or API calls. A probe
compiled with the configured C6 toolchain produced a 280-byte IRAM function with
no undefined symbols. This object result is not final-firmware placement or
callback execution-time evidence. Native ASan/UBSan tests cover wire golden bytes,
truncations, invalid records, atomic rejection, ownership, serial wrap, freshness,
retirement, reconnect, clock/port changes and snapshot barriers.

Integration still must provide authoritative local association admission and call
retirement on connect/reconnect, disconnect and AP-stop events. A received host map
alone must not assert that a station is currently associated. Serialize task updates
with callback reads; keep state and output in DRAM. Clock snapshots need a radio-local
preparation timestamp in the same timebase as activation. Preserve the existing
`departure >= not_before_ps` condition as well as the new activation boundary.
Test event/callback ordering and delayed host updates; no atomic transition claim
is established by the isolated table tests. Logical identities, all three message
paths, the transport multiplexer and actual PortSync/MD state remain unintegrated.

## Logical port registry export

`esp_ptp/ptp_wifi_association.h` now supplies a deterministic allocation and copied
snapshot API. Slot zero uses the physical transport's one-based port number.
Slots 1 through 15 use a separate block above every configured physical port,
with disjoint blocks for each physical transport. For a two-port bridge, the
first AP peer is port 2 and the second is port 18. This allocation deliberately
reserves space for other physical transports; contiguous numbering is unnecessary.
It is a local allocation choice, not a claimed normative numbering requirement.

`ptp_wifi_peers_snapshot` derives identities from stable registry slots. Removing
one peer does not renumber survivors; a reused slot has a new association lifetime.
`ptpd_wifi_association_snapshot` copies under the peer lock and rejects unavailable,
disabled, link-down, non-gPTP, non-wireless and non-AP transports. An empty live AP
returns an empty snapshot. Rejected calls leave the caller's output unchanged.
The copy retains no internal pointers. Callers must still revalidate queued work
at consumption; this is not an atomic transaction with eventual radio transmission.

Native tests exercise four physical transports with all 16 slots, allocation
bounds, survivor stability, reconnect, copied ownership, actual API guards and lock
balance, and conversion through the association wire codec to radio peer selection.
Both P4 and endpoint firmware builds pass. No runtime message path uses this export
yet, and these builds have not been flashed. Announce, Signaling, and FTM still need
coordinated integration, along with local radio admission and PortSync/MD state.

A local radio event must not merely retire the currently known host lifetime:
a delayed first publication for an older host association could otherwise arrive
after a same-MAC reconnect. Before admission, establish a relationship between the
radio's current association lifetime and the host's exported lifetime. Test this
case explicitly, including absence of a prior map and event/publication reordering.
Do not use MAC equality or a reusable association ID alone as proof of lifetime.

## Announce and Signaling source integration, not deployed

AP capability transmission now derives its source port from the same stable slot
allocator. Directed incoming Signaling is decoded against that association's local
identity, after rechecking its captured lifetime. Two-peer tests exercise wrong-peer
target rejection as well as acceptance of the correct logical target.

The Announce mailbox now owns the copied registry, message, enqueue timestamp and
link generation. Its worker emits each copied destination with the corresponding
source port. It no longer performs a station-list RPC. Before each send it rejects
work older than one second, backwards local time or a changed link generation.
Invalid message lengths are rejected instead of truncated. These checks do not
make the final check and radio handoff atomic; that existing boundary remains.
The sender obtains its registry through the gPTP-only export, so non-gPTP AP
Announce fanout is no longer submitted through this helper.

Native tests extract the actual enqueue/worker implementation and cover two logical
identities, copied ownership, queue/task failures, invalid sizes, expiry, generation
change between sends and radio rejection. Actual daemon scheduling tests now check
a second AP peer's outgoing identity. Actual Signaling dispatch tests check directed
requests to the second peer. P4 and endpoint builds pass; neither has been flashed.
FTM still emits the common port-2 template and therefore the current source tree is
not ready for coordinated multi-peer deployment until that path is connected.

For the remaining handoff, the hosted source shows Wi-Fi lifecycle notifications
are posted to the host default event loop, while custom-data callbacks run directly
in RPC decoding. Receipt of a custom response alone therefore does not prove the
host peer registry has processed an earlier lifecycle event. An admission handshake
must account for this queue boundary, not just compare MACs. Native event sending
calls `protocomm_pserial_data_ready`; transport ordering still needs verification
before relying on a host event-loop barrier.

## Radio lifecycle generation and forwarding hooks

`ftm_radio_association.h` tracks the radio AP membership and a generation that
changes on every join, leave or stop. Generation changes are independent of whether
a host map has ever arrived. An old generation therefore cannot authorize a delayed
first map following a same-MAC reconnect. Admission also requires an exact membership
set and a successfully queued lifecycle notification. Boot/publication/freshness
validation remains the separate existing map check. A new `FAG1` envelope contains
the radio generation plus the existing `FAM1` record, totalling 232 bytes; the live
transport multiplexer does not accept this envelope yet.

The coprocessor forwarding patch now exposes begin/complete hooks and propagates
the real `protocomm_pserial_data_ready` enqueue result. The FTM component's begin
hook invalidates timing snapshots and advances local association state under the
callback lock; complete records enqueue success for that exact generation. Symbols
are linked into the C6 firmware and its local registry is in DRAM. These hooks run
in task context, not the timing callback. The C6 build and native admission/actual
forwarding-helper tests pass. This image is archived and not flashed.

Transport inspection shows `protocomm_pserial_data_ready` copies into one request
queue, which one pserial task consumes. This establishes local queue order after
successful enqueue, not end-to-end event delivery or host processing. The custom
response must carry an exportable radio generation and membership. Its host handler
must cross the default event-loop boundary and reconcile the registry before
publishing a map bound to that generation. Reconciliation must reset stale per-peer
state even when ordinary lifecycle notifications were missed. A newer radio event
must invalidate the resulting map before any callback can use it. No current
runtime code yet performs this complete handshake or applies the admission gate.

## Coordinated runtime integration

The host and coprocessor now use private probe protocol version 5 (304-byte
response). It adds the radio's exportable generation and complete MAC set without
adding a custom callback slot. On the host, the response posts a copied event to
the default event loop; its handler checks armed radio ownership and a one-second
age bound before reconciling the AP registry. Reconciliation validates the whole
set first, preserves surviving slots, and resets per-peer state on a new radio
lifetime. Repeating the same epoch is idempotent. A native event after reconciliation
invalidates the export until a newer radio snapshot is processed. No large peer-table
copy is placed on the 2304-byte event-task stack.

A coherent host snapshot carries radio boot and generation into the 232-byte FAG1
map envelope. The existing custom-data mux routes it separately from the 168-byte
timing record. Radio admission checks the local generation, complete membership,
forwarding status, arm-handshake ownership, publication replay and map validation.
Clock snapshots record their preparation start time and require matching local clock
identity. The callback selects at most one association from the newest eligible
clock snapshot, rejects pre-activation snapshots, and writes its full source identity
into the Follow_Up. The existing referred-departure timestamp barrier is retained.
Radio lifecycle and host-boot changes invalidate pending snapshots and admission.

Actual callback-block tests cover both logical identities, unknown peers, referred
old timestamps, activation boundaries, map expiry and radio generation changes.
Actual public API tests cover reconciliation retirement and idempotence; prior
Announce and Signaling tests still pass. All three firmware builds pass. In the
linked C6 image, capture_frame is 766 bytes in IRAM, association_map/radio registry/
preparation timestamps are DRAM, and callback calls are limited to the existing
IRAM timer, critical-section and Follow_Up emitter functions. No new external call
was introduced by the peer selector. Hardware execution-time measurement remains
separate from placement evidence.

This connects identities and lifetime admission. It does not implement all MD or
PortSync state machines, prove multi-station FTM operation on hardware, or complete
802.1AS conformance. Lifecycle processing remains asynchronous to physical radio
association changes; the final API handoff boundaries are not claimed atomic.

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
