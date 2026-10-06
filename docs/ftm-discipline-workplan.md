# End-to-end FTM discipline work, 2026-09-25

Objective: demonstrate disciplined wireless time from the MOTU selected
source using IEEE 802.1AS FTM transport. User target: best achievable error,
with measured limits. Physical alignment and protocol conformance are
separate acceptance requirements.

At 09:03 UTC, FTM-only clock discipline has independent sub-microsecond
bench evidence. Full 802.1AS conformance and reliable audio operation are
not established. The working endpoint requires an exact-blob diagnostic
for discarded reports and an explicitly experimental signed-RTT mode.

Bench: fixed shelf/laptop obstruction; bridge GPIO45 and endpoint GPIO18,
both10x, Rigol DHO804 at192.168.4.78. Historical same-pin channel difference
median2.56ns, not subtracted from the current edge-alignment results.

| Work | Evidence/status |
|---|---|
| Coherent software clock and hardware mappings | Implemented; raw16MHz SYSTIMER, affine clock, paired hardware-edge handshake, generation and freshness guards |
| Source propagation and actual FTM FollowUp | Implemented; upstream origin/time-base metadata, residence correction, hardware-rate readback, bounded IRAM emitter |
| Token association and receiver | Live quartet/IE matches; no observed sequence mismatches in the successful paired runs |
| FTM-only controller | Implemented; initial acquisition step followed by continuous rate steering; beacon phase steering disabled |
| Independent measurement | 90/90 edge pairs within1us across a deliberate5s observation gap; separate loaded run60/60 within1us |
| Loss/status behavior | Holdover and recovery observed; advertised validity dropped and recovered; AVB's3s status cache remains a limitation |
| Loaded data path | Approximately4kAAF packets/s reached bridge ingress and forwarding counters advanced; reservation accounting fixed; packet loss and uncontrolled C6 sample-clock rate remain, so no clean audio pass |
| Portability/conformance | SDK3- and2-frame requests both rejected;8-frame fallback works. Raw report retention, Signaling/asCapable/domain requirements and final normative edition remain unresolved |

The loaded baseline passed: 599/599 measurable edges within 1 us over an
11 minute 26 second run, maximum 991 ns and absolute p95 648 ns. The initial
600th acquisition preceded the first endpoint diagnostic pulse. Full
receiver-load subset: 570/570 within 1 us. RPC concurrency and reservation
accounting fixes remained stable; audio packet loss/playout resets remain.

Announce/path-trace changes now build and pass native tests: preserve the
received path, append this bridge, reject loops/malformed paths, refresh
selected metadata and isolate selected-source receipt timeout from other
traffic. Deployed with daemon-owned queued RX. Endpoint log confirms the MOTU +
bridge path; monitor missed Announce frames. A fresh unloaded 90/90 scope
run stayed within1us (-548..705ns, abs-p95558ns). Queue ownership,
bounds/FIFO/timestamps, path codec and selected-source tests pass ASan/UBSan.

Private beacon timing is now entirely ignored in FTM discipline mode,
including session admission. Fresh acquisition without it succeeded;
90/90 scope pairs remained within1us (-476..815ns). Independent directional
minima were first compared in shadow mode (-13..3ns estimated phase change
over63reports), then enabled:150/150 loaded scope pairs within1us (-553..798ns).
One bridge diagnostic pulse target is missing from the log; do not claim
uninterrupted pulse delivery.

Receive validation now rejects truncated per-type bodies, advertised lengths
exceeding actual data, wrong version and malformed gPTP FollowUp metadata
before clock adjustment. Native sanitizer tests and both builds pass.
Both boards run this update. Another captured MOTU stale-Pdelay timestamp
fault after bridge restart was cleared by the authorized outlet cycle;
endpoint readiness recovered09:02:44. Final scope regression passed60/60 within1us (-624..855ns,p95709),
with63/63 common logged target seconds and no missing/duplicate targets.

Remaining acceptance work:

1. Validate the complete Announce path and selected-source receipt behavior
   on hardware. Test stream cleanup is completing with firmware deployment.
2. Separate timing readiness from protocol capability, including receipt
   timeouts and prompt propagation to audio consumers.
3. Audit/implement full source-change, Announce/path-trace, Signaling,
   requested/granted burst, interval and domain semantics against the final
   standard and applicable corrections. Current minimum-RTT selection also
   now has an optional independent forward/reverse selection implementation;
   final-edition verification and supported small-burst behavior remain.
4. Obtain a supported vendor API for usable quartets/IEs on nonpositive RTT
   and the required burst controls. Concrete request is prepared but unsent.
5. Remove the private diagnostic dependency, repeat restart/source/wrap and
   loaded physical measurements, and resolve reservation/playout failures
   before claiming full AVB success.

Results and limits: ftm-discarded-report-experiment.md. Raw artifacts and
image provenance are in build-ftm-discipline and project.md. Earlier
mapping/codec/backend investigations remain documented in their dedicated
results files. No commits/pushes or external messages have been made.

09:20 source/status milestone: selected source identity and complete path
now survive FTM acquisition and holdover independently of consumer timing
readiness. Finite5s observation-loss test:271/271 management samples kept
MOTU and the full3-clock chain, zero timeouts; readiness dropped/recovered.
GET_AS_PATH also now uses exact wire length, tested with1..17-clock paths.
Both boards run the normal updated firmware with LOSS_TEST off. Final live
queries verify52-byte three-clock responses. Current restart reacquired
without a switch cycle; the earlier switch timestamp fault is not fixed.

Next protocol focus is true asCapable/capability status, per-port Signaling
and domain handling. Existing asCapable remains a legacy readiness mapping;
selection/status separation does not establish protocol conformance.
