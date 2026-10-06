# Association integration hardware test, 2026-09-25

The coordinated implementation carries the same logical identity in AP Announce,
Signaling and FTM Follow_Up. Radio-owned lifecycle generations gate host metadata;
host reconciliation crosses the default event loop and resets stale peer state.
This is identity/lifetime integration, not complete MD/PortSync or conformance.

## Initial loaded failure and correction

All three integrated images were flashed after verifying chip MACs. The first P4
boot encountered the previously observed MOTU Pdelay timestamp fault: consecutive
sequence IDs 30 through 33 carried the identical request-receive timestamp
13572.096655168, while response-origin timestamps advanced. The independent
`association-tap-map.pcapng` preserves this evidence. The authorized Shelly cycle
restored the switch and wired qualification. The outlet was verified back on.

With Class B wired-talker audio forwarded to the wireless listener, the first
65-acquisition scope run failed the sub-microsecond target:

| Run | Paired edges | Within 1 µs | Offset range | Absolute p95 |
| --- | ---: | ---: | ---: | ---: |
| Initial association integration | 65/65 | 41/65 | −2231 to +2928 ns | 2231 ns |
| Elapsed-time mapping cadence | 65/65 | 65/65 | −476 to +850 ns | 780 ns |

Initial run: 14:07:46.950–14:08:50.999 UTC. Endpoint readiness repeatedly dropped.
The mapping edge was scheduled every five request iterations. Added metadata RPC
work stretched 6 of 44 measured edge intervals beyond the 1.5-second freshness
limit; intervals ranged from 1.432 to 1.548 seconds. Mapping state reset and FTM
output paused despite valid upstream timing. The failed capture and summary remain
in `association-loaded-*` and `association-loaded-failure-summary.json`.

The P4 scheduler now uses a 750 ms elapsed-time deadline, leaving RPC margin below
the unchanged 1.5-second validity cutoff. During the repeat loaded scope window,
75 measured edge intervals ranged from 0.746 to 0.997 seconds and all 76 logged
mapping results were valid. No readiness drop occurred in that repeat window.

Repeat run: 14:12:15.871–14:13:19.990 UTC. Median offset was +207 ns. All 65 scope
acquisitions paired, with no rejected arming attempts or missing crossings.
Reported integer-second logs matched for all 64 common seconds, with no missing
or duplicate records. Management queries completed both operations in 152 of 154
rounds; the other two had path-query timeouts. All successful AVB-info replies named
the MOTU clock. This is not zero-loss management evidence.

The repeat 75-second Ethernet capture contained 300334 AAF frames on the wired
outbound tap and 300098 on the switch-to-bridge tap. Dumpcap reported 1 and 47
flushed packets on those interfaces respectively. Do not interpret these counts as
proof of lossless audio. Audio was disconnected afterwards; GET_TX_STATE reported
zero connections. The scope uses 3.2 ns sampling and no channel-skew correction.
Results measure physical bridge-to-endpoint output-edge alignment, not direct
absolute error against the switch's internal clock.

## Recovery and remaining work

The controlled endpoint restart exercised new radio generations 3 and 5 after the
previous generation 1. Host and coprocessor logs agreed on each admitted generation.
After the last rejoin at 14:14:28 UTC, the endpoint reported ready at 14:14:38 UTC.
The unloaded post-reconnect scope run at 14:15:11.782–14:15:45.814 UTC paired
35/35 edges, all within 578 ns. Range was −366 to +577 ns, median +206 ns,
and absolute p95 539 ns. There were no missing crossings or rejected arming
attempts. All 110 management query rounds succeeded and named the MOTU clock;
no readiness transition occurred during the run. A separate five-second capture
contained no AAF frames after disconnection. This establishes the observed
single-peer recovery, not arbitrary event-order or multi-peer recovery behavior.

Still required: simultaneous hardware association tests, media qualification and
PortSync role/state handling, broader source-change/recovery acceptance, and the
remaining normative/vendor API gaps. The loaded result demonstrates a measured
operating point, not a universal bound or IEEE 802.1AS conformance.

## Second associated control peer

A temporary Linux managed interface `ftmtest0`, MAC `02:19:f8:16:a4:67`, joined
the open bridge AP at 14:18:27 UTC using the existing wireless adapter. The original
monitor interface and host Internet interface stayed in place. Host and radio
both admitted generation 6 with two members. The temporary interface was explicitly
disconnected at 14:20:23 UTC and deleted afterwards; both sides then admitted
generation 7 with one member. Endpoint readiness did not drop across these events.
This station is a control-plane peer, not a second FTM initiator.

The independent station capture shows Announce and Signaling source port 18.
All 29 captured Announce frames carried the MOTU BTC, stepsRemoved 1, and exact
84-byte messages containing the path MOTU → bridge. All 111 AP Signaling frames
and 29 Announce frames passed the common-header/reserved-byte checker. This closes
the earlier missing independent wireless Announce path observation for this run.

A finite send-only test established the station's own PTP identity and requested
log interval −3 for port 18. It then sent a stop request from the same station to
port 2, followed by a correctly targeted stop and reset:

| Stage | Observed replies after 250 ms grace | Advertised interval |
| --- | ---: | ---: |
| Port 18 fast request | 46 in 5.750 s | −3 |
| Stop incorrectly targeting port 2 | 45 in 5.751 s | −3 |
| Stop correctly targeting port 18 | 0 in 2.750 s | none |
| Reset port 18 | 3 in 3.750 s | 0 |

Fast-phase mean rate was 7.997 Hz. The wrong-target phase had one 250.4 ms interarrival
gap and mean rate 7.822 Hz; do not claim perfect cadence or lossless delivery.
All six injected messages were independently captured with the expected identities
and targets. Dumpcap recorded 405 packets and zero drops on the managed interface.
The sender and analyzer are `tools/ftm_association/send_peer_interval.py` and
`analyze_peer_interval.py`; artifacts use the `two-peer-*` prefix.

The concurrent scope run at 14:19:45.959–14:20:29.986 UTC paired 45/45 edges, all
within 814 ns. Range −200 to +814 ns, median +262 ns, absolute p95 713 ns; no missing
crossings or rejected arming. There were 37 acquisitions before the second station
disconnected and 8 after. The initial join preceded the scope run, so only logs,
not these waveforms, cover continuity at that join. Audio remained off throughout.
Two simultaneous FTM initiators and their burst scheduling remain untested.

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
