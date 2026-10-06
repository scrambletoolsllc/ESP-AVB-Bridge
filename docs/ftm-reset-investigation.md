# Association and radio reset test, 2026-09-24

Two controlled sequences used the same diagnostic firmware, image SHA256
18eab1ba91be15e46219d083c87cf9b6d9893489ad24c3a2a78bf2b82b782c60,
ELF identity f450429f9... . Each collected a baseline, called
esp_wifi_disconnect at approximately 60 seconds, called esp_wifi_stop then
esp_wifi_start at approximately 120 seconds, and completed at approximately
180 seconds. The existing application handled reconnection. Only the
wireless endpoint was rebooted between sequences; no firmware change was
made between them. The user was asked to leave the bench undisturbed.

| Run and stage | Sessions | Status | Median raw reconstructed RTT |
|---|---:|---|---:|
| Healthy baseline | 118 | All successful | +1.562 ns |
| Healthy after reconnect | 117 | All successful | +1.562 ns |
| Healthy after radio stop/start | 116 | All successful | +1.562 ns |
| Failing baseline | 29 | All status 5 | -10.938 ns |
| Failing after reconnect | 27 | All status 5 | -10.938 ns |
| Failing after radio stop/start | 27 | All status 5 | -10.938 ns |

Each stage covers about a minute. The different session counts reflect the
existing slower retry cadence after failed FTM sessions. Additional records
after completion are preserved separately in the analyses, not mixed into
the stage comparison. Every reset API returned ESP_OK. Logs confirm both
disconnect/reassociation sequences, one endpoint boot per run, no additional
application RX-stall radio recovery, no panic and no diagnostic queue drops.
All complete ordered timestamp quartets agree with their stored RTT fields.
Context words 72/74 remain 0/704 throughout.

These observations show that association reconnect and driver stop/start
were insufficient to clear the captured bad state. They do not prove that
only a full reset can change it, nor that all PHY state was reset by
stop/start. The two run medians differ by exactly 12.5 ns, which is a useful
timing clue but not identification of the internal mechanism. No artificial
RTT offset or calibration adjustment was made.

## Earlier long-run transition and uncertainty

Before this controlled test, the original third diagnostic boot had been
left logging for almost six hours. A saved snapshot contains 15,440 reports,
one boot, zero logged disconnects, and zero application radio restarts.
It was mostly failing until approximately 20:20:22 UTC, then produced 7,534
consecutive successful reports in the saved portion. The nearby 30-report
windows shift from median -4.688 to +7.812 ns. RSSI distributions and T1/T3
remainders modulo 25 ns remain similar across this transition.

The user is not sure whether the endpoint, probes or surrounding objects
moved around that time. Thus this is evidence of recovery without a logged
software reset, but not evidence that internal state alone caused it.
Do not continue to describe this problem as exclusively boot dependent.
The original stream and transition analysis are preserved in
build-ftm-reconnect/prior-long-run.log, prior-long-run-summary.json, and
spontaneous-transition.json.

## Implementation, artifacts and follow-up

CONFIG_FTM_FAILURE_RESET_TEST is default off and requires the existing
internal failure recorder. Its worker logs each action and return value.
The reset-test image repeats the sequence on every boot, so the logging-only
image is restored after testing. The driver/blob timestamp arithmetic and
calibration values are unchanged. The test is not an audio-load or physical
clock-alignment validation.

Reproduce analysis with:

```sh
python3 tools/ftm_failure_probe/analyze_reset.py \
  build-ftm-reconnect/run1.log --require-complete
python3 tools/ftm_failure_probe/analyze_reset.py \
  build-ftm-reconnect/run2.log --require-complete
```

Build/config, flash and identity records, both complete run logs and
analyses, and tap captures are in build-ftm-reconnect/. All source changes
remain uncommitted. The separate unsigned RTT consumer/fallback bug remains
unfixed; it did not cause the driver's all-invalid sessions.

The next discriminating work is to record lower-level timestamp and PHY
initialization state across a full reset, ideally alongside a controlled
longer physical path. The present two context words cannot identify the
state responsible for the observed 12.5 ns difference. An association reset
should not be presented as a recovery workaround based on these results.

## Restored state

The logging-only image was restored and flash-verified:
665963a52eb4315424333a2c5dead9e60abc923399221c7a88a8dc8049d38603,
ELF cf3fa3aa7... . It has no timed reset sequence. The saved initial health
sample contains nine status-5 reports, 126 negative quartets, median
-7.813 ns, no diagnostic drops or timestamp/RTT disagreement, and no panic.
The endpoint remains on this failing boot with internal capture active in
build-ftm-reconnect/logging-restored.log for the next investigation.
