# Paired responder and initiator capture, 2026-09-24

The bridge C6 now records the raw T1/T4 hardware tick values passed by
`lmac_record_txtime` to `wDev_ftm_record_t1t4`, plus the converted timestamps
from the responder session after the original callback runs. The endpoint
continues recording the received T1/T4, its local T2/T3, and the local RX
descriptor timing fields.

The frozen capture contains 433 endpoint reports over 471.140 seconds and
5,953 exactly matched exchanges. All available remote timestamp pairs match
the responder records, including their dialog tokens. There are no
ambiguous matches, diagnostic queue drops, timestamp conversion mismatches,
endpoint descriptor reconstruction mismatches or recorded panics. Entries
with missing timestamps remain explicitly counted. A partial trailing
report, if present, is explicitly reported by the parser.

Matching uses `(T1, T4)` modulo the remote 48-bit counter, not host wall
time, nearest-neighbor matching or the assumption that consecutive logs
describe the same exchange. Multiple responder boots require an explicit
analyzer option; a duplicate timestamp pair across boots remains ambiguous.

## Good and bad states on one endpoint boot

The endpoint was verified and restarted once before capture. It did not
reboot again during this comparison. Bridge resets during installation,
serial logger attachment and a deliberate repeat produced five diagnostic
responder boots. Boot 1 had no FTM records; the other four have paired data.
The same responder image was used throughout these diagnostic boots.

| Responder boot | Matched exchanges | FTM state | Median RTT |
|---|---:|---|---:|
| 2 | 194 | Successful reports | +4.687 ns |
| 3 | 1,789 | Failed reports | -7.813 ns |
| 4 | 210 | Failed reports | -9.375 ns |
| 5, settled 714-tick calibration | 3,732 | Successful reports | +3.124 ns |
| 5, initial 614-tick calibration | 28 | Successful reports, including startup outliers | +6.249 ns |

The deliberate bridge restart was recorded at 22:52:50 UTC. Attaching the
new P4 logger caused an additional bridge restart, so these are reported
as separate responder boots rather than treated as one restart. The
endpoint had association changes but only one `FTMDEBUG_BEGIN` marker.
The P4 and C6 both restarted, so this does not isolate a C6-only reset.

This demonstrates that the observed state can change after bridge restarts
without an endpoint reboot. It argues against a fault confined to initial
endpoint measurements. It does not establish that every bridge reset fixes
the problem, or identify the physical source of the remaining timing bias.

The endpoint's TX-minus-RX phase modulo 80 is **39 in both successful and
failed portions**. Thus the 39-versus-41 association in the earlier three
endpoint boots is not a reliable good/bad classifier. Endpoint compensation
remains 704 ticks, while responder compensation is 714 in the settled good
and bad runs. The relative clock-rate contribution remains a separate
effect, as documented in the earlier rate investigation. The endpoint
metadata totals include 3,952 successful-report entries at phase difference
39 and five at 41; all 1,999 failed-report entries with metadata are at 39.

## A distinct startup calibration transition

In responder boot 5, endpoint reports 162 and 163 use responder compensation
614. The C6 calibration table identifies that value with the disconnected
20 MHz FTM / 40 MHz PHY selection. During report 163 the responder logs:

```
wifi:new:<6,0>, old:<6,1>, ap:<6,1>, sta:<255,255>
wifi:(trc)phytype:CBW20-SGI
wifi:station: fc:01:2c:fd:fe:80 join, AID=1, bgn, 20
```

Tokens 6..13 have RTTs around 3.124..7.812 ns. Tokens 14..19 occur after
that transition while the session still holds compensation 614, and have
RTTs 157.812..160.937 ns. Report 164 starts a new session using 714 and
returns to RTTs 1.562..6.250 ns. The 100-tick difference equals 156.25 ns,
consistent with the observed outlier magnitude.

This is evidence consistent with a stale session calibration across a
PHY/association transition. It is separate from the persistent negative
RTTs, which occur with settled 714/704 compensation at the two ends.
It does not show that these startup outliers train a persistent bad state.
A useful follow-up is to test a fixed 20 MHz AP configuration before Wi-Fi
starts, and invalidate in-flight FTM observations across association/profile
changes. Neither behavior was changed in this capture experiment.

## Instrumentation and validation

`CONFIG_FTM_RESPONDER_PROBE` is default off. The component requires exact
audited hashes for `ieee80211_ftm.o` and `wdev.o`. It wraps the externally
referenced callback, calls the original first, copies bounded data, and
queues without waiting. A separate task formats UART records. Private
session offsets are T1 at 48, T4 at 56, and compensation at 118. The build
does not modify SDK archives or timestamp arithmetic. Linked disassembly
confirms that the real LMAC call reaches the wrapper and the wrapper calls
the original function first.

The `slave_rpc` and `ptp` console tags are limited to warnings in this
diagnostic image to leave UART capacity for the records. The previous
finite MAC calibration experiment is disabled. This adds callback copying
and queue overhead; it is not a timing-neutral or audio-load validation.
It captures the hardware ticks supplied to the callback, not a second
independent RF timestamp or every underlying hardware descriptor field.
Consequently, exact agreement does not establish absolute ranging accuracy.

Responder image SHA256:
`eaae2f47695afb42c0573d726224aad3034763a62fb697c0228064e17f0e5c92`,
ELF identity `364be5579...`. Endpoint image remains
`f06c744a5b0db7da997f35e3cfb91adf79737d9c1f61db1b0b3437abb5f5a943`.
The P4 bridge image is restored unchanged. The fresh six-megabyte backup
matched the P4 restore application byte-for-byte, and its original staging
region was restored after the MAC-checked SDIO OTA update. Prog2 has no EN
connection; direct UART bootloader entry was not assumed.

Eight offline regression tests pass, including exact matching across
remote counter epochs, token and conversion disagreement detection,
unmatched/duplicate pairs and explicit handling of multiple boots.
Ethernet taps were verified after startup and the controlled restart;
their directional mapping remains unchanged. Scope pulse logs continue,
but this experiment makes no independent clock-alignment accuracy claim.

## Reproduction and current state

Artifacts are in `build-ftm-paired/`: build/config, flash and restoration
logs, fresh backup, provenance hashes, linked wrapper disassembly, raw
console logs, frozen endpoint/responder snapshots and analysis JSON.

```
python3 -B tools/ftm_failure_probe/analyze_paired.py \
  build-ftm-paired/endpoint-final-snapshot.log \
  build-ftm-paired/responder-final-snapshot.log \
  --allow-responder-reboots --require-matches
python3 -B -m unittest discover -s tools/ftm_failure_probe -p 'test_*.py'
```

Both diagnostic captures remain active, with the endpoint currently in a
successful FTM run. No automatic reset loop is installed. The persistent
negative-RTT cause is still unresolved; the separate unsigned RTT consumer
bug remains unfixed. No changes were committed or pushed.
