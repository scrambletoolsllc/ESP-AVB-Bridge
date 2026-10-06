# Wired clock prerequisite, 2026-09-25

The bridge must first track the selected wired source before its wireless
clock transfer can be evaluated. A new coherent PTP snapshot exposed an
upstream acquisition problem: the previous PI controller oscillated by
approximately +/-250 us and retained tens of microseconds of offset after
several minutes. Source freshness alone did not indicate phase lock.

The wired controller now uses elapsed observation time, a Q16 integral,
conditional anti-windup and an absolute trim converted to the hardware's
relative frequency adjustment. Beacon controller gains are unchanged.
Native UBSan simulations cover five intervals from 1 ms through 4 s,
opposite oscillator drifts, large initial offsets and saturation. These
check arithmetic and simplified loop behavior, not hardware accuracy.

The first hardware baseline used image
`a25a3148075b86d9c41bce974d37fbce2f960ddd5a2ba53e42bf4a3834ffa39e`.
Over 97.0 seconds, 89 logged snapshots were valid. Reported offset was
-56..+48 ns, median +6 ns, absolute p95 46 ns. Logging sampled about once
per 1.1 seconds, starting 15 seconds after startup, so this is neither
every Sync observation nor a complete acquisition measurement. It also
does not establish independent physical accuracy or path symmetry.

Five simultaneous scope acquisitions still showed CH2 minus CH1 between
-920 and -856 us at an 8 us sample interval. The endpoint remains on the
beacon controller. This is not an end-to-end FTM discipline result.

Artifacts in `build-ftm-discipline/`:

- `host-wired-pi.bin`, `flash-wired-pi.log`, `host-wired-pi-live.log`.
- `wired-pi-initial.json`, `wired-pi-scope.json`.
- `wired-pi-taps.pcapng`, zero capture drops; selected MOTU identity
  `0001f2fffeff3b14`, observed Sync and Follow_Up corrections zero.

The tap mapping changed after reset: f0 wired endpoint outbound, f1 switch
to wired endpoint, f2 bridge outbound, f3 switch to bridge. Reverify after
each subsequent reset.

A separate measurement-only build inlined timer latch operations. Its
linked disassembly contains no HAL calls between the latches, but its
P4 read bracket worsened to 3.425..5.675 us in 78 matched observations.
That window remains a material mapping uncertainty. Removing function
calls did not establish a better measurement. A finite per-core comparison
measured 500..600 ns typical on both cores, including the preceding public
clock and register reads. One observation reached 3125 ns. Pinning the
actual diagnostic tasks to core 0 did not fix their wider brackets; the
pinning change was removed.

The SDK's native Ethernet PPS GPIO route is available only when the P4
minimum chip revision is at least 3.00 (`esp_hal_emac/esp32p4/emac_periph.c`).
This bench P4 is revision 1.3. An experimental route produced no periodic
output and the scope acquisition timed out. That unsupported code was
removed and the scheduled scope output restored. The single connection
transition logged by that experiment is not a PPS measurement.

A subsequent capture change moves result writes after both timer latches.
Linked disassembly confirms that sampled values stay in registers during
the bracket. Both targets build. In 38 matched shared-edge observations, the P4
bracket was 525..575 ns, median 525 ns. A later 139-pulse scope window
showed 525..550 ns P4 brackets. The endpoint's updated image measured
1100 ns brackets, down from 1175 ns. These are interval widths, not clock
accuracy claims. The changed compiled helper contains no result stores or
function calls between the two timer latches.

The latest wired run recorded 137 valid snapshots over 148.6 seconds:
-52..+58 ns offset, median -5 ns, absolute p95 43 ns. It has the same
sampling and independent-accuracy limitations as the first run.
The native PPS experiment is retained only in ignored build artifacts.
