# FTM invalid-measurement investigation, 2026-09-24

Internal logging is implemented and running on the wireless endpoint.
It captures the rejected timestamp buffer before the Wi-Fi driver releases
it, using an isolated build and an exact blob hash gate. See
`tools/ftm_failure_probe/README.md` for the layout, capture mechanism,
record format and analyzer. No driver arithmetic or timestamp callback was
changed, and no SDK library file was modified.

## Controlled observations

Before instrumentation, the normal firmware completed 49,221 successful
sessions over about seven hours with no failures. One endpoint restart
produced 100 successes, while the next produced only status-5 failures.
Those captures are under `build-ftm-recurrence/`. The failing run was
preserved before installing the diagnostic image.

The following three boots used identical diagnostic firmware, ELF identity
cf3fa3aa7..., image SHA256
665963a52eb4315424333a2c5dead9e60abc923399221c7a88a8dc8049d38603.
Only the wireless endpoint was restarted between samples. Bridge firmware,
ranging settings, scope settings and calibration values were not changed.
No physical move was requested during the experiment.

| Boot | Reports | Session status | Median reconstructed RTT | Range |
|---|---:|---|---:|---:|
| 1 | 24 | All status 5 | -9.375 ns | -12.501 to -6.250 ns |
| 2 | 263 | All successful | +4.687 ns | -1.563 to +15.624 ns |
| 3 | 49 | All status 5 | -4.688 ns | -7.813 to -1.563 ns |

Boots 1 and 3 contain 328 and 680 complete, ordered timestamp quartets,
respectively, all with negative reconstructed RTT. They also contain two
and three incomplete timestamp entries, which were classified separately.
The healthy boot contains 3,648 positive, six negative, two zero and twelve
incomplete entries. A successful session can therefore still contain
individual nonpositive measurements.

For every complete, ordered quartet, recomputed RTT agrees exactly with
the stored driver field. All three captures have zero recorder drops and
no panic. The two logged context words stayed at 0 and 704. That does not
establish that all internal PHY state or calibration was identical. RSSI
medians were -59, -53 and -59 dBm across the three boots, so received-power
behavior also deserves controlled investigation.

The immediate rejection mechanism is now observed rather than inferred:
all usable measurements in the failed sessions have nonpositive computed
RTTs. The driver correctly omits them from its positive-RTT average and
returns status 5 with zero public entries. The timestamps are mostly
present and monotonic, rather than absent or randomly corrupted.

This does not explain why the measured RTT shifts between boots. It is
consistent with a small timestamp/PHY bias overwhelming the physical RTT
at this short distance. It is not proof of a particular calibration,
clock phase, multipath or radio-initialization defect. No fixed correction
has been applied to force negative measurements positive.

## Separate unsigned-value defect

The per-entry RTT field is uint32, but the blob stores accepted small
negative differences as two's-complement bit patterns. The application
currently excludes only zero and UINT32_MAX when computing its per-entry
average. The existing C/Python experimental clock models use the same
incomplete filter.

In successful boot 2, report 1 contains -1,563 ps represented as
4294965733. The application's logged average is 306787061 ps; averaging
only positive entries yields 4086 ps. This is captured directly in both
the internal records and the application log. Nevertheless, that report's
injected peer delay remains 2 ns because the application preferentially
uses the valid 4 ns driver aggregate. The inflated per-entry average is
used only when the aggregate estimate is zero. This defect is therefore
separate from the all-invalid driver sessions and does not demonstrate a
307 us synchronization excursion in this run.

No filter fix was mixed into this initial controlled comparison. A follow-up
should exclude every nonpositive signed RTT consistently in the consumer
and experimental models, with regression cases from these actual samples.

## Next controlled iterations

1. Compare association-only reconnect with full endpoint restart while
   preserving this internal capture. This separates association state from
   radio/PHY initialization as far as those operations permit.
2. Record additional PHY initialization and compensation state, based on
   verified symbols/call sites, to identify what changes across good/bad
   boots. The two current words are insufficient to establish root cause.
3. Repeat at a longer physical path or controlled attenuation, one variable
   at a time, recording RSSI and raw signed RTT. Do not treat attenuation as
   additional propagation delay or invent an RTT offset.
4. Fix the separate unsigned-value consumer bug and replay the saved mixed
   reports before repeating the hardware comparison.

The diagnostic image is left running with internal capture active on the
third, failing boot for further investigation. There is no automatic
rejoin/reboot test in this image. Artifacts live under `build-ftm-debug/`:
three boot logs, fixed boot-3 snapshot, analyses, prior uninstrumented
failure, build/flash logs, disassembly, object and image provenance, and tap
captures. Source changes are uncommitted. No new audio-load or independent
clock-alignment claim is made by these tests.

## Subsequent reset tests

See `docs/ftm-reset-investigation.md` for the completed association and radio
restart comparisons. Neither cleared the captured bad state. The earlier
long-running diagnostic boot also recovered without a logged reset, but
possible physical movement at that time is unknown. The issue must not be
described as exclusively boot dependent.
