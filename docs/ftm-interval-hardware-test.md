# Associated-station interval request test

The AP dispatch is implemented and native-tested, but needs a hardware test from
the existing associated C6 endpoint. An Ethernet-host injection cannot prove the
wireless association path. Keep the current scheduler image as the rollback.

Use an explicitly enabled, default-off diagnostic task on the wireless endpoint.
Wait until the AP identity is bound and ordinary capability messages are arriving.
Send independently encoded 58-byte Signaling requests to the associated BSSID,
using the endpoint's real ten-byte PTP source identity and the bridge wireless
port's target identity. Record each request, radio return value and every received
capability message's sequence, advertised interval and monotonic receive time.
The diagnostic must not run in the FTM callback or change clock admission.

The finite sequence should establish initial one-second cadence, request interval
1, and observe nine accepted notices at the old cadence before two-second cadence.
Then request -3 and observe 125 ms cadence, request 127 and observe cessation,
request 126 and observe one-second restoration. Include a wrong source-port
identity request and an unsupported -4 request, neither may change the cadence.
Use a reset request at the end even after a failed assertion. Retain all records;
radio acceptance alone does not prove delivery or receiver behavior. Exercise a
reassociation separately and verify the default interval and fresh lifetime.

Native tests cover station-to-station isolation, but this single wireless endpoint
cannot establish two-station hardware isolation. A second association is required
for that claim. AP physical source port numbering and per-association PortSync/MD
remain separate unfinished requirements. The current nine-notice policy follows
public draft prose; final normative count/boundary review remains necessary.

2026-09-25 first hardware run: finite sequence completed with all seven radio
submissions accepted and the expected received-state changes. Twelve interval-1
notices were observed: the first nine at approximately one second, then periods
2.121, 1.999 and 2.000 seconds. Stop produced zero received indications during its
three-second window; reset restored interval 0 and five notices in five seconds.
Wrong-identity stop and unsupported -4 requests retained interval -3.

This proves functional transitions on one real association, not timing conformance.
The -3 window received 19 indications in three seconds, arrival gaps 70–300 ms.
The scheduler currently schedules from actual dispatch time, so daemon poll
quantization can accumulate. Investigate deadline-based pacing and separate TX
acceptance timestamps from RX task timestamps before attributing all jitter.
Do not loosen the target or call the median cadence a full timing pass.
Evidence: build-ftm-discipline/interval-probe-result.json and the endpoint probe log.

Deadline pacing repeat, 2026-09-25: AP now includes capability deadlines in its
poll timeout and preserves the deadline across small scheduling delays. A fully
missed period is skipped, without draining a backlog of sends. Native simulation
with a 20 ms polling grid produces 80 sends in ten seconds at log interval -3.

The hardware repeat sent and received all 56 fast-rate notices, no sequence gaps.
Submission rate was 7.999889 Hz; intervals 119657–130372 us. Queue-to-submission
latency was 33–246 us and the radio call took 40–734 us. Endpoint arrival rate was
7.982677 Hz over the matched finite window, gaps 69862–180122 us. This isolates the
former mean-rate drift to scheduling, while receive-side jitter remains. It does
not establish an over-air timestamp or a normative interval tolerance.

Functional transitions passed again. Stop had one final arrival 49.811 ms after
the request submission, then no more during the three-second window. The test
allows a 250 ms grace period to account for in-flight messages; do not call this
an instantaneous-stop guarantee. Reset restored one-second indications.
Evidence: capable-deadline-result.json and capable-deadline-tx-result.json under
build-ftm-discipline, plus both serial logs and the captured Ethernet startup.

STA receive-direction test, 2026-09-25: the bridge sent the finite request sequence
and the associated endpoint changed its capability transmission rate. All stages
passed the functional checker: 31 initial notices, 12 slowdown notices, fast
windows of 23/16/17 notices, no notices during stop, and five after reset.
All 56 fast-rate transmissions arrived at the bridge, no sequence gaps. Bridge
receipt rate was 7.999973 Hz (109.0–141.0 ms gaps); C6 radio submission rate was
7.969872 Hz across the matched finite span (97.8–161.7 ms gaps). C6 queue delay
ranged from 571 to 23462 us, radio calls from 120 to 439 us. Do not infer exact
per-packet cadence from the mean rate. Source/path checks passed 253/253, with no
post-acquisition FTM readiness loss or peer-delay loss in this run. See
sta-interval-probe-result.json, sta-interval-tx-result.json and both probe logs.

Wired request procedure: send finite unicast Ethernet frames addressed only to
the bridge from the controller NIC's own MAC. The PTP source identity is supplied
from a fresh captured Pdelay response on that bridge link, and the target is the
bridge's captured port identity. This is deliberate protocol test injection,
not evidence that the MOTU emits these requests. Capture both directions with
dumpcap; use captured request arrival times and bridge Signaling transmission
times for the functional checker. The sender restores interval 0 via request 126
in its final cleanup. Keep wrong-identity and unsupported-rate cases in the run.
