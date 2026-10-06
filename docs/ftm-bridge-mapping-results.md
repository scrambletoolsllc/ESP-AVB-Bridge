# Bridge mapping validation, 2026-09-25

The P4 now runs a read-only bridge MAC-to-PTP mapping check. It uses paired
40 MHz hardware captures and rejects identity/generation changes, missing
sequences, wide brackets, MAC discontinuities and stale snapshots. Four raw
edge observations estimate the oscillator ratio. The applied Ethernet rate
converts this ratio into the PTP domain. SDIO receive time only determines
freshness, not phase.

The first implementation used the wired controller's requested trim. In
342 live predictions its residual ranged from -2025 to +719 ns, median
-589 ns, absolute p95 1486 ns, with growing negative bias. Inspection found
integer truncation in relative hardware frequency updates and in conversion
of absolute controller targets into relative adjustments. Thus the requested
trim is not an exact representation of the applied hardware rate.

The second image reads Ethernet addend, increment, rollover mode and clock
selector coherently around the sample. It rejects an update in progress.
Both supported clock sources derive from the same oscillator as the GPTimer.
Binary rollover rate is calculated using the actual integer increment, not
its requested nanosecond accuracy. No wired servo behavior was changed.

At 06:12:17 UTC, this image had 161 valid maps and 159 subsequent predictions:

| Internal measurement | Result |
| --- | --- |
| Prediction residual | -955..+992 ns |
| Median residual | -22 ns |
| Absolute residual p95 | 823 ns |
| Read-bracket uncertainty | 1151..1176 ns, median 1163 ns |
| Sampled wired offset, 168 observations | -70..+50 ns, absolute p95 41 ns |
| Requested minus applied trim | 31..600 ppb |

There was one bracket rejection: edge 89 had a 114-tick (2850 ns) P4 read
window. It reset acquisition; four subsequent valid edges restored the map.
No panic/assert was found. The increasing trim discrepancy without growing
mapping bias supports using the applied register rate. It does not establish
the oscillator or physical error budget under every operating condition.

Limitations: these predictions share the capture path. The reported bracket
uncertainty excludes fixed skew, upstream asymmetry, rate change during
holdover and endpoint error. This is not an independent scope measurement
or an end-to-end FTM accuracy result. The endpoint still uses beacon timing.
The controller's requested/applied trim divergence remains a separate
long-term actuator-accounting issue even though the mapping now avoids it.

Evidence under `build-ftm-discipline`: `host-bridge-map-live.log`,
`bridge-map-requested-rate-summary.json`, `host-bridge-hwrate-live.log`,
`bridge-hwrate-summary.json`. Reproduce with
`python3 tools/ftm_bridge_clock/analyze.py LOG`.

Deployed P4 image: `host-bridge-hwrate.bin`, SHA256
`1e0b57d3c45f26467dcbe81ae9ae96d5427da073c6196d8be52087bf059763dd`.
MAC was checked before flash and flash hashes verified. The final source
also rejects a derived negative epoch or unrepresentable output rate; those
additional invalid-input guards passed native tests and a P4 build but were
not reflashed into this ongoing run. The FollowUp codec is not active on air.

Stable taps reverified after reboot: f0 wired outbound, f1 switch to wired,
f2 bridge outbound, f3 switch to bridge on enp1s0f*. Capture:
`bridge-hwrate-stable-taps.pcapng`. The earlier startup capture had incomplete
link traffic and must not be used for directional mapping.

Next integration: source/mapping snapshot transfer to the C6, exchange-bound
FollowUp generation, endpoint admission and FTM-only discipline. Avoid
further accuracy claims until that path is enabled and physically measured.
