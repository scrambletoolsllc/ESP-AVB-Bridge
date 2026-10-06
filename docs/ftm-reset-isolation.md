# Endpoint and bridge reset isolation, 2026-09-25

Nine short windows contain 144 reports and 1,982 exactly matched exchanges.
Each window contains 16 complete reports, with responder output allowed to
drain before matching. All validated windows have zero unmatched available
pairs, ambiguous matches, token errors, timestamp conversion disagreements,
RX reconstruction disagreements, diagnostic queue drops or recorded panics.
Entries lacking remote timestamps remain counted separately.

The endpoint averaging-fix image and AP20 bridge image were unchanged.
Endpoint-only resets verified MAC fc:01:2c:fd:fe:80; bridge resets verified
80:f1:b2:d2:ca:a9. Logger attachment can cause another hardware reset, so
bridge reset sequences include the identity-read reset and the subsequent
P4 logger-attachment reset. Multiple responder boot segments are explicit.
One early logger attachment was refused because esptool still held the port;
it was retried only after esptool exited, without forcing the port open.

## Observations

RTT columns are in ns; RSSI columns are endpoint/responder in dBm.
Adjusted RTT subtracts each exchange's estimated relative-rate contribution;
it is diagnostic, not calibrated distance. Responder RSSI zero values are
counted separately as unavailable, rather than included in its median.

| Window | Matched exchanges | Raw median RTT | Rate-adjusted median RTT | Median RSSI |
|---|---:|---:|---:|---:|
| baseline | 224 | 3.124 | 8.664 | -59.0 / -53.0 |
| endpoint1 | 222 | 6.250 | 12.442 | -58.0 / -52.0 |
| endpoint2 | 222 | 4.687 | 10.882 | -58.0 / -52.0 |
| bridge1 | 220 | 12.499 | 18.001 | -64.0 / -66.0 |
| bridge1-later | 222 | 7.812 | 13.347 | -66.0 / -68.0 |
| bridge2 | 206 | 12.499 | 17.985 | -67.0 / -69.0 |
| bridge2-later | 222 | 10.156 | 15.996 | -69.0 / -70.0 |
| position2-baseline | 222 | 6.250 | 12.422 | -69.0 / -70.0 |
| position2-settled | 222 | -4.688 | 0.832 | -67.0 / -68.0 |

The first two endpoint-only resets left the responder on the same global
console boot, number 16. Median RTT changed, while compensation remained
704 at the initiator and 714 at the responder. The endpoint coarse
TX-minus-RX phase modulo 80 remained 41 in all nine windows. Its median
folded receive correction remained approximately 175 to 178 ticks.
These fields alone do not distinguish positive and negative states.

The first bridge sequence reached responder boot 18. Its later no-reset
window changed from +12.499 to +7.812 ns. Thus the offset is not a fixed
constant determined solely at boot. Both direction RSSIs also fell markedly.
The user confirmed something moved around 02:56 to 02:58 UTC. Those bridge
comparisons are therefore confounded by the RF environment and must not
be used as clean causal evidence for a reboot effect. Endpoint-only changes
also do not establish which end's hardware is responsible: reassociation
changes state at both ends, and ordinary within-boot variation is present.

## Repeat after the reported movement

At the current position, a fresh baseline and a bridge reset were captured
while the endpoint stayed on its second boot. The first post-reset window
failed strict parsing because a responder UART line joined/truncated two
records. That raw window is preserved with position2-bridge-invalid.json;
it is not counted as validated data. A new capture without another reset
produced the fully matched position2-settled window.

Median raw RTT changed +6.250 to -4.688 ns. Endpoint/responder median RSSI
changed -69/-70 to -67/-68 dBm, substantially closer than the earlier
movement-confounded comparison, but not proof of identical RF propagation.
Rate was approximately -53.135 versus -52.999 ppm; median rate contribution
changed only -5.534 to -5.519 ns. Per-exchange adjusted median RTT changed
+12.422 to +0.832 ns. The positive-to-negative change therefore cannot be
explained by that small rate change. Medians of separate distributions need
not subtract to the median of their differences.

All matched responder compensation remains 714; every initiator report has
704. No 614/706 startup transition occurred in these validated windows.
The known coarse phase difference remains 41 in both positive and negative
states. The remaining offset is not localized to one device by this test.

## Next diagnostic boundary

The existing responder probe sees raw T1/T4 ticks after their hardware
fields have been combined. Local disassembly shows lmac_record_txtime reads
three slot registers at 0x600a54f0/4f4/4f8 minus slot*116, rereading the same last word, to form coarse time, phase and folded receive
correction before calling wDev_ftm_record_t1t4. The current probe cannot
separate these contributions. The initiator already records analogous
receive-descriptor fields.

A useful next instrumentation change is to capture those responder input
fields after the original timestamp read, then verify that they reconstruct
exactly the raw T1/T4 for the same exchange. Any post-read capture must be
validated against slot reuse and register read semantics before it can be
trusted. No new MMIO read hook was installed in this test. Ordinary timing
variation, RF multipath and private PHY calibration remain possibilities;
none has been established as the cause. Do not subtract a guessed constant.

## Artifacts and running state

All window logs, JSONs, reset identities, scripts and summary.json are in
build-ftm-isolation/. capture.py retains the real boot header when windowing
an existing stream; it includes recent responder history to cover delivery
latency. It rejects damaged records instead of repairing or silently removing
them. The later script bounds that history by record count instead of bytes.

Firmware SHAs remain: endpoint70ca1591ca068ab4a6cc0fa97d03d0c466635c59075218be077b686b1c86cc4c,
P4f24ccd1e83527433cd20593c8f279b8f12f022b0236d936be9d678c75979440a,
responder eaae2f47695afb42c0573d726224aad3034763a62fb697c0228064e17f0e5c92.
No new firmware or scope/audio accuracy test was needed for this experiment.

Live logs: endpoint2-live.log, position2-bridge-live.log, and the unchanged
build-ftm-paired/responder-console.log. No restart loop runs in the background.
Final tap verification found a mapping change: f0 wired endpoint outbound,
f1 switch toward wired endpoint, f2 switch toward bridge, f3 bridge outbound.
Use that mapping only after re-verifying it at the next bench change.
