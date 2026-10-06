# Peer-delay transaction audit

The 2026-09-25 correction fix confines Pdelay correction fields to the peer
exchange. The actual handler regression covers zero, signed nonzero and
rejected negative delays, and asserts that the Sync correction is unchanged.
Public 802.1AS revision D8 equation 11-6 gives response correction minus
Follow_Up correction. Neighbor rate conversion is still missing, and the
existing correction decoder rounds to integer nanoseconds.

The next change must make the exchange coherent across the esp_timer TX task
and PTP daemon RX task. Adding identity comparisons alone will not do this:

- TX currently increments a shared sequence and writes `delayreq_time` while
  RX reads them. Publish an immutable request record containing sequence,
  full requester identity, TX timestamp, monotonic deadline and generation.
  Invalidate the prior record before sending, send outside the lock, then
  publish only if its generation has not been invalidated in the meantime.
- A response can arrive before TX timestamp publication. Explicitly handle
  this ordering, or reject and retry the next exchange without using a
  provisional timestamp. Never hold a critical section over network I/O.
- RX must match the full requester identity and request sequence before
  clearing the unanswered counter or updating responder cardinality.
  Currently cardinality is updated in dispatch before transaction admission.
- Retain T1 with the admitted response's T2 and T4. Match Follow_Up against
  that response's full responder identity, requester identity and sequence.
  Consume once, reject expired or generation-invalidated exchanges, and
  reject invalid timestamp nanoseconds before arithmetic.
- Invalidate pending transactions on link/profile changes and clock steps.
  Announce source changes currently clear the mutable T1 seconds field;
  this must not race TX publication or leave an old response usable.
- Multiple responders, duplicate responses and missing Follow_Up need
  explicit outcomes. Per-request cardinality and fallback state must not
  race between TX reset and RX updates.
- Cover send failure, publication races, sequence wrap, wrong ports with
  matching clock IDs, late/duplicate messages, link loss and source/clock
  changes in native tests. Then compare accepted wire exchanges and scope
  behavior on the bench before deriving wired asCapable from them.

This audit does not claim full per-port ownership or BTCA support. Timing
handlers still use port zero; injected frames now retain ingress for
Signaling, but that does not make all timing handlers multiport.

References, cross-check only; no implementation code copied:

- https://1.ieee802.org/wp-content/uploads/2019/03/802-1AS-rev-d8-0.pdf
- https://github.com/richardcochran/linuxptp/blob/master/port.c

## Implementation update, 2026-09-25 09:49 UTC

The request, response and Follow_Up now use `ptp_peer_exchange.h` under a
short shared critical section. TX publishes only after successful timestamp
completion and only if the generation remains current. Early RX is rejected
and retried on the next exchange, rather than using a provisional timestamp.
The immutable request includes sequence, requester port, T1 and monotonic
deadline. The response adds T2, T4 and full responder port identity.
Follow_Up requires the same identities/sequence, a live deadline and an
unconsumed response. Invalid nanoseconds, negative or greater-than-one-second
local/remote intervals are rejected. Two-step responses are required.

Link changes, profile reset, selected source changes and clock steps
invalidate pending state. Request publication, response admission, consumption
and invalidation use the same lock. Responder multiplicity is checked only
after matching the live request, including source port, and invalidates the
exchange. Peer-delay responses injected on another port cannot affect port0.
The unanswered counter is reset after admission, under the publication lock.

Native ASan/UBSan tests cover 70000 sequential exchanges (sequence wrap),
wrong requester/responder ports, duplicate messages, expiry, multiple peers,
missing response, invalid nanoseconds and invalidated publication. The actual
sender is tested with early RX, send failure, missing timestamp and
invalidation during send; network I/O is asserted outside the lock. The
actual Follow_Up correction regression still passes. Both firmware builds
pass; bench deployment is in progress.

Remaining limits: neighbor rate ratio is still unity; correction decoding
rounds to integer nanoseconds; out-of-order Follow_Up before Response is
dropped. Existing profile/link fields and servo/status state do not all use
this new lock. In particular, invalidation after measurement consumption
but before averaging remains a lifecycle edge to audit. Endpoint-declaration
TLVs are still inspected before transaction admission. Capability must not
be asserted from these changes alone. Failed/missing TX timestamps currently
do not increment the successful-request unanswered counter.

## Rate and commit update, 2026-09-25 09:56 UTC

`ptp_peer_rate.h` estimates remote/local rate from successive matched
response receive timestamps and corrected responder transmit timestamps.
The correction on responder transmit time is the Follow_Up correction.
Differences are formed relative to each clock's own previous timestamp,
so unrelated epochs do not lose precision. Intervals from10ms to10s and
ratios within1000ppm are admitted; gaps, nonmonotonic observations, peer
identity changes and lifecycle changes invalidate the estimate and reanchor.
Two accepted observations are required before updating the delay.

The remote turnaround, including signed fractional corrections, is divided
by remote/local rate before subtraction from local RTT. The result is stored
as local nanoseconds, rounded only at final publication. Native tests use
+/-100ppm with30ms turnaround and500ns propagation, a case where the unity
assumption biases delay by1500ns. Tests also cover unrelated epochs, signed
fractional corrections, peer/lifecycle changes, stale history and bad rates.

Measurement consumption now carries both request generation and lifecycle.
Rate calculation runs outside the lock; final rate/delay commit checks both
again under the lock. An actual-handler regression invalidates the exchange
between consume and commit and verifies that delay is not published. Each
request advances generation without advancing lifecycle; link/profile/source
changes and clock steps advance both.

These changes supersede the unity-rate, integer-correction and
consume-before-commit limits above. Remaining work includes standards
performance qualification, capability expiry/admission, old averaged delay
retention when a different peer first reanchors, endpoint-declaration TLV
admission, and broader profile/servo/status ownership. Rate invalidation
does not yet itself revoke the legacy wired asCapable flag. No AnnexB
performance or final-standard conformance claim is made. Public D8
11.2.19.3.3 and11.2.19.3.4 are the available reference text.

## Capability update, 2026-09-25 10:04 UTC

Wired management asCapable now requires an enabled live Ethernet port,
gPTP domain0, fresh qualified peer measurement in the current lifecycle,
valid measured rate, copper-link mean delay no greater than800ns and a
nonlocal responder clock. Both messages must carry majorSDO1/minorSDO0.
The published flag is independent of source selection and FTM readiness.
Wi-Fi remains false. A changed peer or lifecycle clears old averaging state.

Duplicate responses, duplicate Follow_Up and self-responses now invalidate
the exchange and revoke qualification; a duplicate from the same responder
does not trigger the separate legacy multiple-responder fallback. Full
request matching happens before this fault handling.

Native actual-status tests prove selected source alone is insufficient,
valid link capability survives loss of source selection, and stale
qualification expires. Helper tests cover link/enable/profile/domain and
lifecycle conditions. Actual Follow_Up tests cover800ns boundary and larger
delays. Self and duplicate rejection tests pass.

The three-request-interval expiry is deliberately conservative and is not
the final allowedLostResponses/allowedFaults state machine. Nonzero domains
remain false pending neighbor Signaling negotiation. Timing/BTCA processing
is not yet gated by the new qualification state, so the flag alone is not
a full protocol implementation. A live finite peer-exchange-loss experiment
is still needed to verify management expiry and recovery on hardware.
Reference: public D8 11.2.2/Table11-1/domain0 backward-compatibility condition.

## Completed-exchange loss accounting, 2026-09-25

The request sender previously incremented the AVB Lite unanswered counter at
publication and cleared it on Pdelay_Resp. That counted the current request
before its deadline and concealed a missing Pdelay_Resp_Follow_Up.

`ptp_peer_expire()` now counts each published, incomplete request at most once
at its monotonic deadline. It distinguishes missing response and missing
Follow_Up, saturates consecutive losses, and preserves counts across requests.
A matched completion clears consecutive losses; lifecycle invalidation clears
all counters. Failed sends and missing TX timestamps are not peer losses.
Expiry runs before replacement by a new request and during endpoint fallback
checks, under the existing peer lock. `PDELAY_LOST,count,missing_follow_up`
reports losses retired by the sender outside the lock.

The existing AVB Lite nine-loss policy now uses expired incomplete exchanges.
It is an application fallback policy, not the gPTP asCapable state machine.
Bridge fallback remains disabled. The three-interval capability watchdog and
immediate fault revocation remain unchanged pending the normative audit.

Native ASan/UBSan tests cover 70,000 losses, saturation, deadline equality,
once-only counting, missing Follow_Up, mismatched and late completion,
lifecycle reset, and ten consecutive actual sender calls. Existing exchange,
actual correction handler, timing admission, source refresh, and status tests
pass. P4 and C6 firmware builds pass. These images are archived but not yet
flashed; current deployed images remain the independently measured timing-gate
baseline.

### Normative discrepancy to resolve

Public 802.1AS-Rev D8.0 sections 11.2.13.5 and 11.5.4 describe faults as bad
rate-ratio computation or delay above threshold, with default allowedFaults=9.
Figure 11-9 instead immediately clears capability for those faults when the
responder is not this clock, and routes self-response to the fault counter.
Its increment-after-comparison also needs checking against the final text.
Do not claim the draft diagram and prose are equivalent or silently choose
one and call it conformance.

The freely accessible March 2021 correction sheet changes Figure 10-18 only:
https://standards.ieee.org/wp-content/uploads/import/documents/erratas/802.1AS-2020_errata.pdf
The separate technical corrigendum project is:
https://1.ieee802.org/maintenance/802-1as-2020-cor1-corrigendum-to-ieee-standard-802-1as-2020/
Its linked D4 document requires authentication (401); no access attempted
beyond that denial. Final normative text remains unavailable locally.

## Early-response race reproduced under Class B traffic, 2026-09-25

The capability-gated firmware discarded a matched response if its transmit
request had not yet returned the hardware T1 timestamp. This was intended to
avoid using a provisional timestamp, but Class B traffic made the response
arrive before publication repeatedly. The switch had responded correctly.

The diagnostic run logged 55 expired exchanges, each with exactly one matching
response and only the unpublished-T1 rejection bit. Response handling preceded
publication by 8 to 1064 us (median 218 us). During the loaded segment, consecutive
losses revoked wired capability and invalidated the timing snapshot; the wireless
endpoint entered holdover. `peer-rx-loaded-scope-summary.json` contains 100
acquisitions, 92 measurable pairs, only 49 within 1 us, and maximum measured
offset 15854 ns. Eight acquisitions had no paired crossing in the capture window;
that does not prove eight absent physical pulses. This run includes load and
recovery after disconnect, not 100 uniformly loaded acquisitions. Wire capture
confirms 40000 AAF packets in a 10-second interval at both talker egress and bridge
ingress. Prior unloaded scope success did not cover this failure.

The corrected transaction retains an early matched response in its existing
bounded storage, without consuming T1 or changing the clock. It can also retain
one matched Follow_Up until publication. Only successful TX timestamp publication
makes that pair eligible. Send failure, absent timestamp, generation invalidation,
duplicates and expiry prevent use. The daemon replays retained Follow_Up with an
expected-generation check; the transmit timer never executes servo work. Polling
is capped at 1 ms only while an unexpired retained Follow_Up awaits completion.
No network operation or logging is performed with the peer lock held.

ASan/UBSan tests cover early response plus early Follow_Up, successful publication,
cancellation, lifecycle invalidation, duplicates, expiry, stale deferred-generation
handling and actual sender failure paths. Both target builds pass. The corrected
bridge is deployed for the same loaded comparison; endpoint firmware is deliberately
unchanged to isolate the bridge fix. Hardware comparison results follow below.

### Corrected loaded hardware result

The bridge-only correction passed the repeated Class B load test. The capture
`peer-early-loaded.pcapng` confirms 40000 AAF packets per ten seconds at both
wired talker egress and bridge ingress. Scope window 11:00:32.053 through
11:02:11.002 UTC remained loaded throughout: 100/100 measured pairs within
1 us, -426.379 to +951.994 ns, median 238.193 ns, absolute p95 604.395 ns.
No rejected arming, empty waveform, or missing paired crossing occurred.
The corresponding whole-second serial window contains 99/99 common target
seconds, without gaps or duplicates. This is output-edge alignment, not a
direct measurement of the MOTU's internal clock.

`PDELAY_EARLY` reached 81 completed early exchanges at the end of the scope
window and 97 before disconnect. The first retained response preceded T1
publication by 1738 us. No PDELAY_LOST or post-acquisition capability drop
occurred. The endpoint stayed FTMREADY throughout load.

Management produced 182 rounds: 178 BTC replies all named the MOTU, and 179
path replies all contained the complete three-clock path. Four AVB-info and
three path queries timed out under load; none returned a different source.
Management/audio transport loss remains separate unfinished work. Talker
connection count returned to zero after disconnect.

Comparison artifacts: `build-ftm-discipline/peer-delay-race-comparison.svg`
and `.png`, alongside both scope JSON captures and summaries. Plot axes now
expand to include all measured offsets, rather than hiding failures beyond
1.5 us. The pre-fix plot includes post-disconnect recovery; the corrected
100-acquisition run is entirely loaded. This closes the reproduced early-T1
publication race, not the remaining conformance gaps.

September 25, Follow_Up loss diagnostic:
The wireless capability loaded run lost completion for sequences 55, 77, 90
and 103. The tap proves both response and Follow_Up arrived for 55, 77 and 90;
103 is outside the finite capture. See `wifi-capable-missing-followup-wire.tsv`.
Ethernet DMA missed-frame counters increased under load, but aggregate counts
cannot identify the affected PTP frames. Existing L2TAP consumed counters also
cannot distinguish successful enqueue from its queue-full tail-drop path.

New bounded instrumentation counts matching Follow_Up frames before L2TAP
and handler visits/rejection bits within the pending exchange. Expiry emits
`PDELAY_LOST_FU,sequence,ingress,handler_visits,rejection_mask`. Handler visits
include replay of an early retained Follow_Up. Rejection bits are inactive1,
faulted2, expired4, requester8, no response16, timestamp32, responder64,
duplicate128. Foreign sequences do not affect a pending exchange. Counters
saturate. The ingress diagnostic is independent of daemon allocation lifetime;
only integer state is touched inside the existing short peer lock. No receive
logging or allocations are introduced. This does not modify admission policy.

Hosted transport review found a separate concrete blocking path:
`avbnet.c` forwards audio synchronously from its Ethernet receive callback.
The active `transport_drv_ap_tx()` copies the frame and calls `esp_hosted_tx()`.
In the SDIO implementation, that function calls `_h_queue_item(...,
HOSTED_BLOCK_MAX)` and ignores its return value. On this target the timeout is
`portMAX_DELAY`, and the wrapper calls `xQueueSendToBack`. Thus a full SDIO
queue can block the Ethernet receive task indefinitely. The existing avbnet
comment claiming queue-full returns ESP_ERR_NO_MEM is incorrect for this tree.
This is a source-proven scheduling risk, not yet a proven explanation for the
captured missing Follow_Up frames. The DMA-missed counter is consistent with
receive starvation but does not establish causality. A bounded data-queue send,
correct buffer release on failed enqueue and error propagation should be
validated against the current loaded baseline, preserving control/RPC policy.

Bounded hosted data enqueue correction:
AP and STA frames now use zero-timeout queue insertion. Failure releases the
transport-owned buffer through its supplied free callback and returns
ESP_ERR_NO_MEM. The transmit semaphore is posted only after successful enqueue.
Serial/RPC, Bluetooth and other control traffic keep their existing blocking
policy, but failed enqueue is now handled instead of being reported successful.
The native test compiles the actual function and actual release macro, testing
both buffer modes, accepted/rejected ownership, priorities, invalid input,
transport-down and null callbacks. ASan/UBSan pass. The change is preserved in
`patches/esp-hosted-bounded-data-tx.patch`; reverse dry-run matches the active
managed component. The P4 build passed. Hardware comparison follows.

Bounded enqueue hardware result: 187 queue-full rejections were counted during
this run, demonstrating that the new failure path is exercised. No peer-delay
expiry or post-acquisition capability drop occurred. The loaded scope recorded
65/65 edges within 882 ns, absolute p95 606 ns, with all target seconds present.
Management returned 121/121 MOTU identities and 119/121 full paths; two path
queries timed out. DMA missed counts remained 8 to 11 per nonzero ten-second
read, so the specific missing-Follow_Up cause remains unresolved. The prior
diagnostic run also had no peer loss; do not infer a causal cure from this run.
The capture reports drops (including 220 flushed on the bridge-ingress tap),
so it is not evidence of lossless audio. Scope measurements are independent.
