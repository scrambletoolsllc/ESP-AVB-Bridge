# Clock mapping probe

Enable `CONFIG_FTM_CLOCK_PROBE=y` on both the bridge and coprocessor.
The component is disabled by default. It does not adjust either clock.
A private custom RPC exchange runs every 200 ms, outside the PTP task.
Requests and responses include boot identities and a sequence number.

The bridge brackets its PTP clock with local monotonic microseconds.
The coprocessor brackets reads of the Wi-Fi MAC clock and AP TSF with
its local monotonic microseconds. Both sides record RPC timestamps.
The MAC getter returns 32-bit microseconds, distinct from the FTM
report's 48-bit picoseconds. Their relationship still requires measurement.

Capture the bridge serial log, then run:

```
python3 tools/ftm_clock_probe/analyze.py path/to/serial.log
python3 -m unittest discover -s tools/ftm_clock_probe
```

The analyzer separates boot identities and rejects malformed exchanges,
duplicates, and impossible timestamp ordering. It reports clock-read
brackets, transport RTT, fitted relative rate, and an offset interval
conditional on that rate. An interval with negative width rejects the
model. Low midpoint jitter does not establish accuracy: constant path
asymmetry can produce a stable but biased offset. Independent clock
measurement is still required. Large PTP changes are flagged; the PTP
clock is not used to fit the raw P4/C6 clock relationship.

MAC unwrapping assumes adjacent samples are less than 2^31 microseconds
apart. Do not combine captures separated by longer gaps. TSF zero means
unavailable. Disable sleep during the MAC-clock characterization.

For the bench SDIO updater, first verify the P4 MAC with esptool. Its
updater checks the onboard C6 MAC before writing. Stage the C6 application
as a little-endian uint32 length followed by the binary at P4 offset
0x400000. Wait for image validation and UPDATE COMPLETE before replacing
the updater with the bridge application. Preserve normal firmware and
restore both devices and the staging partition after testing.

The responder callback records the previous exchange's full-width FTM
T1/T4 and a bracketed MAC/local-clock observation at callback entry.
Only the latest callback is included in each RPC response; gaps in its
sequence are expected. The six-byte diagnostic IE carries no timing data.
`FTMCLOCK` records are separate from RPC `CLOCK` records.

For this ESP32-C6 SDK build, disassembly of
`esp_wifi_internal_get_mac_clock_time()` shows one read at 0x600ad000.
The diagnostic callback reads that register directly because the getter
is in flash and Wi-Fi APIs are forbidden in the callback. Reverify this
address against the linked getter before changing targets or SDK versions.
The callback and its callees were checked in the ELF's IRAM section.
This register access is a diagnostic dependency, not a production API.
The callback is later than the FTM ACK it reports, so their difference
includes interframe scheduling; it cannot certify clock offset accuracy.

## Onboard shared-edge capture

`CONFIG_FTM_CLOCK_PROBE_EDGE=y` enables a board-specific hardware
experiment. The Waveshare schematic connects P4 GPIO6 through R52 (0 ohm)
to C6 GPIO2. P4 generates a five-microsecond pulse approximately once per
second. Both chips use a GPIO ETM event to latch a 40 MHz GPTimer on the
same rising edge. Scheduling determines when the pulse occurs, but not
its captured timestamp. No additional wire is assumed.

The P4's Ethernet PPS routing API is unsupported on revision 1.x: the
SDK signal table exposes the route only for minimum chip revision 3.0.
The experiment therefore uses captured GPIO pulses rather than PPS.

Both sides preserve the hardware latch before using software captures to
bracket their local clock read (P4 PTP, C6 MAC). Other code must not call
`gptimer_get_raw_count()` on these timers because it overwrites the latch.
C6 uses an IRAM GPIO ISR; P4 owns pulse generation and reads its latch
from the generating task before producing the next pulse. No alarms or
other capture users are attached to these timers.

`HOSTEDGE` records host boot, host edge sequence, edge ticks, before ticks,
PTP nanoseconds and after ticks. `EDGECLOCK` records host boot, C6 boot,
C6 edge sequence, MAC microseconds, edge ticks, before ticks, after ticks,
ISR local microseconds, RPC receive local microseconds, host request PTP
nanoseconds, host response PTP nanoseconds and echoed host edge sequence.
Only the latest C6 capture is transported. Sequence mismatch is rejected;
production recovery after a missed edge needs an explicit resynchronization
protocol. Boot identities separate timer restarts.

```
python3 tools/ftm_clock_probe/analyze_edges.py path/to/serial.log
```

The analyzer reports local clock-read brackets and cross-chip capture
repeatability. This does not measure fixed propagation/capture skew or
independent absolute accuracy. A constant GPIO-capture bias and FTM
counter calibration error are invisible to linear-fit residuals. Reject
wide brackets and stale observations before using anchors for discipline.
The C6 ISR must run before a subsequent edge overwrites its latch.

The option is disabled by default. GPIO9, GPIO54/EN, SDIO and the Prog2
UART remain assigned to their existing functions.

The edge option also adds `ftm_timer_pair.c` to the GPTimer driver target
for this build only. It accesses the driver's private HAL and spinlock to
put lock/function overhead outside the two counter captures bracketing a
single 32-bit peripheral register read. No installed SDK source is edited.
This is a diagnostic SDK dependency that must be reviewed when upgrading
IDF, not a public production timer API. ELF inspection must confirm that
the helper and its C6 ISR callees reside in IRAM/ROM.

For P4, the sampled register is the Ethernet PTP nanosecond register.
Seconds, update flags and the digital/binary mode are checked around the
bracket, and a separate public clock API bracket checks the direct reader.
Conversion handles binary subseconds identically to the SDK HAL.
For C6, the sampled register is the MAC microsecond register described
above. The MAC quantization interval is still one microsecond even if
the software bracket becomes narrower.

The initial 80 MHz GPTimer request was invalid: the clock divider must
be at least two. Both capture timers use 40 MHz from the 80 MHz source.
The failed diagnostic was recovered over Prog2 UART, with the P4 GPIO54
supplying C6 EN reset and Prog2 DTR controlling IO9. Recovery artifacts
and a minimal P4 reset-controller app are in `build-ftm-pps/`.

## Initiator observation

`analyze_endpoint.py` consumes `FTMLOCAL` records from the isolated endpoint
probe in `build-ftm-endpoint/`. The saved patch adds logging inside the
existing FTM report owner, after its sole `esp_wifi_ftm_get_report()` call.
Do not register another consumer of that report buffer. Each record holds
local-before microseconds, MAC microseconds, local-after microseconds,
dialog token, T2 picoseconds, T3 picoseconds and raw RTT picoseconds.

```
python3 tools/ftm_clock_probe/analyze_endpoint.py path/to/endpoint.log
```

Use one uninterrupted boot per input. The unit-rate MAC/local interval
allows one microsecond of relative quantization uncertainty in addition
to the measured read bracket. A negative interval width rejects the
constant-offset assumption. This is a conditional consistency check,
not a bound on calibrated FTM phase. The apparent T3-to-report age assumes
FTM and MAC share an epoch; callback latency cannot prove that assumption
or reveal a constant counter bias. Local T2/T3 retain more than 48 bits; the analyzer counts crossings of
that boundary separately from backwards wraps. Apparent report ages use
the 32-bit MAC microsecond period and must be less than half that period. Invalid RTT entries are
excluded. The probe does not change the endpoint servo.
