# C6 MAC transition calibration results, 2026-09-24

The FTS-inspired local mapping test ran on the identity-verified wireless
ESP32-C6 endpoint fc:01:2c:fd:fe:80 (revision v0.2), with its normal AVB
application, Wi-Fi association and FTM ranging active. Existing hardware
scope pulses remained enabled. Only this endpoint was flashed; bridge P4
and responder coprocessor firmware were unchanged.

## Results

| Read method | Rounds | Transitions | Training interval width | Held-out violations |
|---|---:|---:|---:|---:|
| GPTimer capture + MAC API | 120 | 51,966 | 825 ns | 0 |
| Direct MCPWM counter + MAC API | 66 | 36,643 | 250 ns | 0 |
| Direct MCPWM and MAC registers | 120 | 12,055 | 225 ns | 0 |

Every usable round in each run produced the same training midpoint and
width within that run, at 25 ns counter granularity. Midpoints from
separate boots are not directly comparable because timer origins differ.
The GPTimer and final direct-read runs completed all 120 rounds and
released their diagnostic timers. The intermediate MCPWM/API run was
intentionally stopped after 66 rounds to test the faster direct method.
Rejected observations are counted in the JSON summaries; counter-wrap,
non-adjacent MAC values, and wide-bracket observations are excluded.

## Method and interpretation

Each round uses 1024 attempts to intersect transition intervals, then
1024 fresh attempts to check whether their intervals include the training
midpoint. Single observations bracket two MAC reads with hardware timer
reads. Only adjacent MAC values qualify. No critical section waits for a
transition. The task yields every 16 attempts and pauses between rounds.

The MCPWM counter runs at 40 MHz with a 60,000-tick period and no output
GPIO. Its result is fine phase modulo 1.5 ms. A coarse epoch anchor is
still needed for a full timestamp conversion. Direct MAC reads match the
linked SDK getter at 0x600ad000; startup API-bracket checks passed. Direct
MCPWM reads apply the SDK HAL's next-count correction for the fixed UP
mode. This private register use is specific to the verified C6/SDK.

The 225 ns interval improves on the 825 ns GPTimer result, but is NOT
225 ns measured synchronization error, RMS jitter, or a certified absolute
bound. Fixed counter/read bias and the relationship to FTM timestamps are
not independently calibrated. No FTM servo was enabled, and no new
cross-board synchronization accuracy claim follows from this experiment.
The stable midpoint also does not prove tens-of-nanoseconds accuracy.

Scope pulse post-checks passed throughout the captured runs and no panic
was logged. Some FTM sessions had invalid RTTs (status 5), already present
before the MCPWM calibration started. These are separate from rejected
local calibration reads. No audio stream was established for this test;
existing bandwidth-admission failures mean it is not an audio-load test.

## Follow-up

Use the faster MCPWM mapping as a candidate for a high-resolution local
MAC-time source, with coarse epoch reconstruction and explicit validity.
Repeat the mapping experiment on the bridge C6 responder, then test a raw
FTM offset/rate model using independent hardware output measurements.
Retain the P4-to-C6 shared-edge mapping and upstream source/vendor-IE work
for connection to wired AVB time. Validate fixed bias, reboots, clock
rollovers and actual audio load before adopting the mapping in the servo.

## Reproduction and artifacts

Source: components/mac_transition_probe/ and tools/mac_transition_probe/.
The feature defaults off; five analyzer tests pass. The disabled P4 build
passes and has no MAC transition diagnostic symbols. No shared component
or SDK source edits were needed, and no commits or pushes were made.

Ignored build-mac-transition/ contains serial logs, three firmware images
and configs, flash/build logs, disassembly, firmware-sha256.txt, per-method
JSON summaries and health-summary.json. The active endpoint image is the
saved endpoint-direct.bin. After completion the diagnostic task is gone;
the normal application and scope output remain running. It runs again on
reboot while its isolated build config remains enabled.

## Hot-path audit after the measurement

The measured direct-read image still loaded the MAC register address
between the first MCPWM read and the two MAC reads. Its task-only sampler
also used SAFE critical-section wrappers with redundant ISR-context checks
outside the measured bracket. The source now preloads both addresses and
uses a four-load inline assembly block, with normal task critical-section
wrappers. The rebuilt ELF confirms exactly four consecutive peripheral
loads in the bracket, with no calls, branches, stores or arithmetic.

This tightened image has been built and inspected but NOT flashed or
remeasured. The 225 ns results above remain from endpoint-direct.bin,
not the new endpoint-tight.bin. Disassembly and the new image/hash are in
build-mac-transition/. Peripheral access latency and fixed counter bias
remain separate from instruction overhead; no hardware floor is claimed.

## Review superseding the initial active-image checkpoint

The subsequent [diagnostic audit](mac-transition-audit.md) found and fixed
an omitted quantization allowance, analyzer failure-accounting gaps,
long-pause/counter-discontinuity checks and sampling-phase aliasing.
The revised four-load firmware has now been flashed and tested: 120/120
usable rounds, 12,096 transitions, zero held-out violations and a 250 ns
interval including quantization. The old 225 ns number excluded that
allowance and is not the revised interval. Active firmware is now
endpoint-dither.bin; details and hash are in the audit document.

## Bridge responder replication, 2026-09-24 06:47 UTC

The onboard responder C6 now passes the same reviewed four-load diagnostic.
Normal bridge firmware was built with the default-off component enabled in
an isolated config; the earlier GPIO2 shared-edge diagnostic remained off.
The linked ELF confirms four consecutive timer/MAC/MAC/timer loads, and the
runtime direct-register/API bracket check passed. CPU frequency is 160 MHz
with power management disabled. Its 1000 Hz RTOS tick makes rounds shorter
than the endpoint's 100 Hz tick; the sample/yield algorithm is unchanged.

| Board | Usable rounds | Accepted transitions | Combined interval | Held-out violations |
|---|---:|---:|---:|---:|
| Wireless endpoint, previous run | 120/120 | 12,096 | 250 ns | 0 |
| Bridge responder, this run | 120/120 | 11,330 | 250 ns | 0 |

The responder sampled for 146.077151 seconds, rejecting 10,817 observations
with its existing timing/counter gates. All training midpoints agreed at
25 ns granularity. The accepted read brackets were 250 ns; the intersected
mapping interval is also 250 ns including the quantization allowance.
This remains a conditional local phase constraint modulo 1.5 ms, not
measured cross-board clock accuracy or a fixed-bias calibration.

FTM ranging and normal SoftAP operation ran throughout the test. From
06:47:26 through 06:49:53 UTC, endpoint logs contain 289 successful reports
and 3,994 valid entries, no FTM failure logs and no panic. The endpoint
logged 148 scope postchecks and the P4 logged 127; all logged checks passed.
The lower P4 count under load does not establish uninterrupted 1 Hz output.
The Rigol at 192.168.4.78:5555 timed out, so no physical edge comparison was
made and no scope settings were changed.

### Admitted audio load and separate failure

A wired-talker to wireless-listener connection was admitted at 06:48:14
and disconnected at 06:50:07 UTC. The responder retained the same interval
through the loaded portion. A 12-second four-tap capture shows about 7,279
AAF packets/s at the wired source and 7,276/s at bridge ingress. Capture
losses prevent treating those counters as an exact network-loss estimate.

Audio delivery itself did not pass: P4 EMAC missed-frame counters and PTP
follow-up mismatches appeared, and the listener reported sequence gaps,
concealment and underruns. Its final stream counters were 677,160 packets,
127,950 sequence gaps and nine underruns. Loss continued after the
calibration released its timer at 06:49:53, including 11,059 additional
sequence gaps in the following ten-second report. This does not identify
root cause or establish that the diagnostic has zero effect; it separates
the local mapping pass from the unresolved forwarding/audio failure.
The connection count was verified zero after disconnect, and normal FTM,
bridge heartbeats and pulse postcheck logs continued. No switch reboot
was needed.

### Deployment and preserved evidence

P4 identity 80:f1:b2:d2:ca:a9 was verified with esptool. A fresh 6 MB P4
flash backup was saved before using the existing SDIO updater. The updater
verified responder identity d8:85:ac:fa:2c:58 and confirmed OTA validation
and activation. The exact saved P4 scope image, partition table, bootloader
and original staging bytes were restored with write verification. The
GPIO45 LDO4 fix remains present. The Prog2 EN pin was not needed.

Current responder image: build-mac-transition/coprocessor/network_adapter.bin,
SHA256 75a1575d199d4c22ebac7f8ea214075f585442791b7b21acc5811e9d53eae1f5.
The finite diagnostic has stopped and released MCPWM; normal responder
operation continues. It will run again after reboot while enabled in this
image. The endpoint and P4 scope images are unchanged.

Artifacts under build-mac-transition/: coprocessor-summary.json,
coprocessor-health.json, coprocessor-calibration.log, coprocessor-console.log,
coprocessor-image-manifest.json, coprocessor-four-load-check.txt,
responder-audio.pcapng and its analysis, isolated build/config, updater and
restore logs, host/endpoint excerpts, and pre-update flash backup. Eleven
analyzer tests and the native UBSan interval tests pass. No commits/pushes.

Next timing work: reconstruct coarse epochs, collect and model raw FTM
T1..T4 offset/rate, then compare hardware outputs independently. Retain
explicit boot/source validity and the upstream P4/shared-edge/vendor-IE
integration. Resolve audio forwarding losses before claiming loaded
end-to-end synchronization performance.
