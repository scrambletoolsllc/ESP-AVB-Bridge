# Shared-edge clock mapping experiment, 2026-09-22

## Physical path and hardware constraints

The board already connects P4 GPIO6 to C6 GPIO2 through R52 (0 ohm).
This was verified in the [Waveshare schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-POE-ETH/ESP32-P4-WIFI6-POE-ETH-Schematic.pdf)
and by matching hardware captures on both chips. No additional jumper
or modification to the Prog2 wiring was needed.

P4 revision 1.3 cannot route Ethernet PPS through the GPIO matrix using
the SDK API. Its signal table exposes PPS only for minimum revision 3.0;
the attempted API call returned ESP_ERR_NOT_SUPPORTED. The working
experiment instead generates a GPIO pulse and hardware-captures the
same rising edge on both chips using GPIO ETM and GPTimer. Generation
jitter changes the pulse time, but does not timestamp it in software.

Both timers use 40 MHz from an 80 MHz clock source. An initial 80 MHz
request triggered the timer driver's minimum-divider assertion. The
C6 was recovered via Prog2 UART: a small P4 application controlled
GPIO54/EN while Prog2 DTR held IO9 low for download entry. UART esptool
verified C6 MAC d8:85:ac:fa:2c:58, then rewrote the active application
at 0x1f0000. The corrected application booted and initialized SDIO.
The other OTA slot, NVS and bootloader were preserved during recovery.

## Capture ownership

Each hardware latch must be read before any software counter capture
replaces it. The C6 GPIO ISR saves its ETM capture first. The P4 generating
task saves its local capture before producing another pulse. No other
code reads those GPTimers, and neither timer has an alarm callback.

The diagnostic attaches P4 PTP and C6 MAC clock observations to the
captures, preserving read brackets, boot identities and edge sequences.
RPC carries recorded timestamps; its latency is not used as a clock
phase measurement. Sequence mismatches are rejected rather than silently
pairing different edges. Recovery after a missed interrupt needs an
explicit production resynchronization handshake.

The optional `ftm_timer_pair.c` helper is compiled into the GPTimer driver
for this diagnostic build, without editing installed SDK sources. It
holds the driver's own lock across two counter captures and a single
peripheral register read. This removes lock entry/exit overhead from the
measured bracket. It relies on driver internals and is not a production
API. The helper and C6 ISR callees were checked in IRAM.

P4 samples its PTP nanosecond register, checking seconds and update flags
around the bracket and validating the direct reader against the public
clock API. Binary-subsecond conversion follows the SDK HAL. C6 samples
the MAC timer register, with its documented one-microsecond quantization.

## Initial measurements

- Public-API PTP sampling: 302 paired edges over 333.7 s, no sequence
  mismatches. Local neighboring-edge interpolation residual p99 0.045 us,
  maximum 0.056 us. These are raw timer captures, not PTP or FTM accuracy.
- Verified audio traffic with the first direct-reader variant: 61 paired
  edges over 67.2 s, no mismatches. Neighbor interpolation residual maximum
  0.081 us; causal prediction from the previous four edges maximum
  0.380 us in this short run. The wire carried about 4,000 packets/s.
- A single rate fit over several minutes is inadequate: the independent
  oscillators drift. Short-window updates are necessary.
- The initial P4 PTP read bracket was typically 3.2 us and could widen
  considerably under load. The C6 MAC bracket was 1.4 us before the helper.
  Read brackets and quantization remain separate from edge repeatability.

One stream connection succeeded at the control layer without producing
packets. Taps confirmed the missing traffic. The authorized five-second
Shelly reset cleared this reservation stall, and packet forwarding
resumed. Samples collected before actual traffic resumed are not counted
as a loaded run. The switch reset also changed the upstream time epoch.

## Paired-read helper under load

The final helper run paired all 119 edges over 133.09 seconds with no
rejections. P4 read brackets were 0.600 us median and 0.625 us maximum;
C6 MAC read brackets were 0.775 us throughout. C6 ISR latency reached
11.775 us, but the ISR retrieved the already captured hardware edge.

Neighbor interpolation residual was 0.141 us p99 and 0.175 us maximum.
Causal prediction using the previous four edges was 0.640 us p99 and
0.676 us maximum. A single raw-counter fit over the entire run reached
44.6 us error; a single fit to disciplined PTP reached 256 us. These
results support a short-window raw-counter mapping and separate PTP
anchors, not one long-lived affine PTP mapping. Audio forwarding was
active during this run; the stream was disconnected afterward.

Artifacts: `pair-loaded-analysis.json`, `edge-pair-loaded.log`,
`tested-images/pair-host.bin` and `tested-images/pair-coprocessor.bin`.

## Interpretation and next implementation requirements

This resolves the physical P4/C6 clock-transfer path. It does not yet
establish one-microsecond end-to-end FTM synchronization.

Keep the raw timer mapping separate from the P4's disciplined PTP clock:
clock corrections and rate changes produce large deviations from a single
PTP-versus-raw affine fit. The production timing snapshot must represent
source generation, rate/correction information and validity, rather than
mistaking those adjustments for cross-chip capture jitter.

The next production protocol needs an arming/resynchronization handshake,
freshness and bracket-quality gates, bounded drift/holdover, explicit
clock-step invalidation and upstream source identity/validity. The
initiator FTM-to-local mapping and independent absolute-error measurement
are still required. The diagnostic's sequence equality assumes no extra
or missed GPIO interrupts since boot; that is not a complete recovery
protocol.

Neighbor interpolation uses a future edge, so it is not a realtime
accuracy result. Causal four-edge prediction is also only a raw-timer
repeatability measure. Neither observes fixed capture/propagation skew,
FTM counter calibration or endpoint clock error.

Artifacts are in ignored `build-ftm-pps/`: logs, analyses, capture files,
firmware hashes, helper disassembly and UART recovery tools. The component
and analyzers are under `components/ftm_clock_probe/` and
`tools/ftm_clock_probe/`. All probe options default off.

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
