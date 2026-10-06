# Initiator clock-domain experiment, 2026-09-22

The wireless endpoint was identified as fc:01:2c:fd:fe:80 before flashing.
An isolated copy of esp_ptp adds logging inside the existing FTM report
handler, after its single report retrieval. It brackets the MAC-clock
getter with esp_timer_get_time, then logs each report's T2, T3 and RTT.
The normal shared component and endpoint servo were not changed.
The probe uses the normal C6 ES8311 pin assignment (19/20/22/21/23,
I2C 8/7, PA 6). Its source patch, image/config hashes and serial log are
saved in ignored build-ftm-endpoint/.

The MAC and software timer have different origins. Bracketed observations
can establish a local conversion, while report delivery is delayed by
several milliseconds and sometimes much longer. Report arrival is not a
hardware receive-time anchor. T3 minus T2 was typically about 104 us,
with another group near 116 us. Local T2/T3 continue above 2^48 picoseconds. They are not truncated like
the responder wire timestamps; treating all four fields as 48-bit values
would discard information. MAC sampling independently wraps at 2^32 us.

The analyzer's MAC-to-FTM report-age calculation assumes a common counter
epoch. Positive, plausible scheduling delays support that hypothesis but
do not measure a fixed FTM counter bias. The MAC/local interval separately
includes read brackets and quantization, and assumes unit relative rate.
A negative width rejects that assumption. None of these checks certifies
absolute FTM synchronization accuracy.

An audio connection attempt during this endpoint run completed at ACMP
but failed admission in the bridge (13,632,000 bps requested, rc=-2).
The endpoint received TALKER_FAILED code 3. All four taps were rechecked;
there was no audio flow. The connection was disconnected. These samples
are not labeled a loaded audio run. This is distinct from the successful
loaded shared-edge run documented separately.

Final capture: 440 reports, 6,115 valid RTT entries over 331.48 seconds,
zero malformed records. T3 crossed 2^48 once without wrapping backward.
The constant MAC/local offset interval was [-108479, -108477] us,
including brackets and relative quantization. Median read bracket was
4 us, p99 12 us and maximum 652 us. Apparent final-T3-to-report age was
1.739 ms minimum, 5.505 ms median and 217.154 ms maximum. Wide software
brackets must be quality-gated; report latency must never be treated as
clock phase. The analyzer initially assumed all timestamps were 48-bit;
observing local T2/T3 above that boundary corrected that assumption.
Twelve analyzer tests pass, including the local full-width boundary,
invalid RTT exclusion and rejection of a stepped constant-offset model.

Restoration completed: normal patched bridge P4, onboard C6 and wireless
endpoint firmware restored, plus original P4 staging partition. Flash
hashes verified. Both endpoints rediscovered BTC 00:01:f2:ff:fe:ff:3b:14.
Final endpoint log recorded 113 successful FTM reports, median raw RTT
43.972 ns. A bridge restart cleared the reservation
problem: a fresh audio connection forwarded about 4,000 packets/s, with
19,924 wired-outbound and 19,915 bridge-ingress packets in independently
timed five-second tap captures. This verifies flow, not a packet-loss
rate or clock accuracy. Tap mapping changed after restart and was
reverified. The test stream was disconnected and serial ports released.
No commits or pushes were made.
