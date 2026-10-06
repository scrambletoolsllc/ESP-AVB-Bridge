# Responder fine-field capture, 2026-09-25

The responder now captures the input fields used to construct its hardware
T1/T4 values, in addition to the raw and converted timestamps already logged.
The endpoint still captures its corresponding T2/T3 descriptor fields.
The attenuation covering is part of the bench setup; keep it and the board
positions fixed when comparing windows. Its material was requested but was
not yet known when these results were recorded.

## Probe acceptance

CONFIG_FTM_RESPONDER_RX_METADATA is default off. This diagnostic build scans
16 timestamp slots AFTER the original wDev callback. It records only a
stable, unique match to both original raw timestamps as valid. Register
reads are not used to alter timestamps, compensation or the clock servo.
Logging remains in a worker. The lmac object is hash-gated along with the
existing Wi-Fi objects. See tools/ftm_responder_probe/README.md for the layout,
equations, log schema and reproduction commands.

The first implementation mistakenly decoded correction from a fourth word.
Its hardware check found zero exact matches and those fields were rejected.
A candidate retained TX-matching fields for diagnosis; corrected decoding
uses bits 7..17 of the third word, which also contains RX phase and coarse
time. The original disassembly repeatedly reads that same word. The earlier
note in ftm-reset-isolation.md was corrected. Synthetic native/Python tests
alone did not establish this layout; exact hardware reconstruction did.

The final image was installed via MAC-checked SDIO OTA. Each attempt restored
the original six-megabyte P4 backup, including NVS and staging, with hash
verification. The backup application matched the AP20 host image. Prog2
has no EN connection; no direct C6 UART bootloader entry was assumed.

## Validated windows

Two complete endpoint windows contain 32 reports and 443 exact paired
exchanges. Both use the SAME responder console boot 35 and the SAME endpoint
boot. There was no reboot between the two windows. The surrounding responder
windows independently verify 268 and 371 original nonzero timestamp pairs;
the extra records cover earlier history and logger drain beyond the selected
endpoint reports. Three records had missing original timestamps and were
reported separately. There were zero missing/nonunique/unstable fine-field
matches, reconstruction disagreements, pair ambiguities, available-pair
losses, token mismatches, diagnostic queue drops or recorded panics in the
validated windows.

The scan duration was 6..35 microseconds, median 7 microseconds. This includes
possible preemption and excludes the rest of the wrapper, queueing and UART
logging. It is added diagnostic work, not a timing-neutral or CPU-cycle
benchmark. The original timestamp capture precedes all of these reads.

| Window | Matched exchanges | Raw median RTT | Responder RX-minus-TX phase, typical | Endpoint TX-minus-RX phase |
|---|---:|---:|---:|---:|
| Earlier, mixed successful/failed reports | 221 | -4.688 ns | 61 | 41 |
| Later, successful reports | 222 | +7.812 ns | 63 | 41 |

Compensation is 714 at the responder and 704 at the initiator throughout.
The responder folded-correction median is 176 ticks; the endpoint median is
about 177 ticks. The earlier window has 125 exchanges from successful
reports and 96 from failed reports. Successful reports can contain negative
individual entries; report status is not an entry-level sign classifier.

The phase distribution shift is NOT a sufficient good/bad discriminator:

| Responder phase | Earlier count / median RTT | Later count / median RTT |
|---|---:|---:|
| 61 | 132 / -6.250 ns | 28 / +7.812 ns |
| 63 | 87 / -3.125 ns | 191 / +7.812 ns |

For phase 61, the median sum of both receive corrections changes from 358 to
367 ticks; for phase 63, from 344 to 351 ticks. Overall correction medians
hide this conditional change. Both coarse phase and fine correction must be
examined together. This is a decomposition of recorded timestamps, not proof
that either quantity is an erroneous hardware correction.

For all 443 joined exchanges, the two ends' fields reproduce the fine RTT
identity modulo the one-microsecond coarse step, within two picoseconds of
integer rounding. The join also verifies each end's raw reconstruction,
responder conversion, exact remote timestamp pair and dialog token. Thus
no discrepancy was found in the observed conversion/delivery arithmetic.
This cannot establish actual RF propagation time or distinguish multipath,
PHY estimation bias and calibration error without another controlled test.

## Artifacts and current state

build-ftm-responder-meta contains backup, all OTA/restoration logs, failed
initial captures, the corrected build, linked disassembly, two validated
windows, independent field summaries and joined CSVs. corrected-joined.csv
and settled-joined.csv contain per-exchange phase, correction, rate, RTT,
RSSI and compensation from both ends. phase-groups.json records the above
conditional comparison. Failed initial metadata uses a different field count
and is intentionally rejected by the corrected parser.

Current C6 image SHA256:
db9d2786fff1426ad2e691a54099c1b5ec33251f114ab250502b2b54099397bd.
Endpoint remains70ca1591ca068ab4a6cc0fa97d03d0c466635c59075218be077b686b1c86cc4c;
P4 remainsf24ccd1e83527433cd20593c8f279b8f12f022b0236d936be9d678c75979440a.
Native UBSan reconstruction tests, two new Python tests and nine existing
failure/paired tests pass. No source was committed. No new scope or audio-load
accuracy claim is made.

Live loggers: endpoint build-ftm-isolation/endpoint2-live.log; responder
build-ftm-paired/responder-console.log; host host-corrected-live.log in this
build directory. No automatic restart loop is active. Final tap mapping is
f0 wired endpoint outbound, f1 switch toward wired endpoint, f2 switch toward
bridge, f3 bridge outbound, verified in taps-final.pcapng.
