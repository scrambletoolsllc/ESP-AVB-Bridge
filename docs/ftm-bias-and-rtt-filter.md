# RTT filtering and short restart comparison, 2026-09-25

The shared PTP client now excludes zero and values above INT32_MAX when
averaging per-entry RTT and choosing its last valid timestamp anchor.
Small negative RTTs are stored in the unsigned driver field as two's
complement values, so checking only zero and UINT32_MAX was insufficient.
The portable C relative-clock model and Python replay model use the same
positive-entry selection. The diagnostic failure analyzer intentionally
retains its legacy-average calculation to identify old affected reports.
No rate correction or new clock servo is enabled by this change.

## Existing continuous capture

The frozen endpoint capture contains 5,593 reports over 12,250.199 seconds:
60 successful, 5,532 status 5, one status 3. One endpoint boot, no diagnostic
queue drops, no panics, and no classified RTT-field disagreements were
recorded. All five associations occurred during the original startup and
controlled restarts; there was no subsequent logged reassociation. No
one-minute interval from minute two onward had a positive median RTT.
This does not mean every individual measurement or report was negative.

For failed reports after sequence 72, the median relative clock rate was
-53.172 ppm, contributing approximately -5.539 ns over the local reply
turnaround. Raw RTT median was -6.250 ns; the median of individually
rate-adjusted RTTs was -0.078 ns. Medians of separate quantities need not
subtract to the median of their differences. The rate calculation assumes
stable propagation within each report and is not a calibrated distance.

At 01:01:35 UTC the previous firmware logged an average of 3,988,179,118 ps
with RTT_est=1 ns. The driver estimate took precedence and peer_delay was
zero; this example did not produce a millisecond delay injection.

The long responder UART log contains malformed/truncated records, despite
no diagnostic queue-drop count. Therefore the overnight evidence above is
endpoint-only, not a claim of a complete paired capture. Original snapshots
are retained in build-ftm-bias/overnight-{endpoint,responder}.log.

## Short comparison after the filter fix

Endpoint MAC was verified, the new image flashed with hash verification,
and the endpoint remained on one boot during the comparison. The bridge
was deliberately reset once; attaching its P4 logger caused an additional
reset. The responder firmware and 20 MHz AP setting were unchanged.

The first 116 complete reports span 69.507 seconds. Exact timestamp/token
matching found 1,573 exchanges with no unmatched available pairs,
ambiguities, token errors, raw conversion errors, RX reconstruction errors,
panics or diagnostic drops. All matched responder compensation values
were 714. Rate fits use complete timestamp quartets, including negative
RTTs; they do not apply the production positive-entry selection.

| Responder segment | Matched exchanges | Raw median RTT | Rate | Rate-adjusted median RTT |
|---|---:|---:|---:|---:|
| Already running, endpoint just reflashed | 1,060 | 0.000 ns | -53.316 ppm | 5.556 ns |
| After deliberate bridge restart | 96 | 14.062 ns | -52.906 ppm | 19.566 ns |
| After P4 logger attachment reset | 417 | 3.124 ns | -52.899 ppm | 8.625 ns |

The rate contribution stays near -5.5 ns while the remaining offset changes
substantially. Thus clock-rate difference explains much of the close-range
negative RTT in one settled state, but does not explain the restart-dependent
offset. Paired records verify delivery/conversion, not hardware RF accuracy.
The startup 614/706 compensation transition did not recur in this window.

The fixed firmware logged avg_rtt=1562 ps with only 3/14 valid entries,
rather than accepting negative unsigned fields. Other mixed reports also
show reduced valid counts and small averages. The final endpoint SHA256 is
70ca1591ca068ab4a6cc0fa97d03d0c466635c59075218be077b686b1c86cc4c.
The bridge image remains the previous AP20 image; its STA-only averaging
path is unused. Forced-reset and forced-disconnect test modes remain off.

## Reproduction and limitations

Artifacts and scripts are in build-ftm-bias/. compare-boots.py freezes the
first validated 116 endpoint reports. Responder data starts at 02:49 UTC,
retaining the actual current-boot header with an explicit window note.
Earlier overnight damaged UART records are outside that time window.
A later live snapshot briefly had 12 unmatched entries in its final report
because responder UART output had not yet drained; it was not counted as
verified data. The frozen window is fully matched.

Checks: 25 raw/model Python tests, nine failure-analyzer tests, native session
and signed-RTT gates under UBSan, native C model tests under UBSan, and
C/Python replay agreement on 713 recorded reports (maximum prediction
difference below 0.000001 ps). Firmware build and flash passed. Taps were
reverified after restart, with the existing directional mapping retained.
No scope accuracy or audio-load test was performed. Changes are uncommitted.

Next useful isolation is determining which local or responder hardware
phase/calibration state changes with these offsets. Repeat controlled
endpoint-only versus bridge-only resets with bounded paired captures and
compare raw descriptor timing fields. Avoid treating an empirical offset
subtraction as a clock accuracy fix before that source is understood.
