# FTM startup transient, 2026-09-24

The bridge now sets WIFI_BW20 before starting its FTM SoftAP. The shared
PTP client serializes session start, cancellation and report handling on
the Wi-Fi event loop. Association changes invalidate the current session;
a canceled session remains pending until its terminal report arrives, so
an old completion cannot be mistaken for a new same-peer session.
Rejected successful reports release their driver report buffer.

A fresh clock beacon is required both before starting FTM and before
accepting its result. It must arrive after association, contain known TSF
and gPTP markers, and be no more than one second old. This deliberately
makes FTM depend on the bridge's clock beacon publication. It is not a
fixed startup delay or a change to timestamp compensation. Existing beacon
clock discipline continues independently. This guard cannot detect every
radio transition before Wi-Fi reports it; repeated bench tests are evidence,
not a guarantee that every possible startup ordering is covered.

## Investigation sequence

1. Fixed AP bandwidth alone, retaining the previous endpoint image:
   paired captures had 248 matched exchanges across two new responder boots,
   all at compensation 714. The earlier 614 to 714 transition and roughly
   156 ns spike did not recur. Negative settled RTTs remained.
2. Session invalidation: a diagnostic-only fifth-session disconnect at
   50 ms returned ESP_OK, canceled the burst, discarded status 6, reconnected
   and resumed measurements. This tested the initial guard before adding
   beacon freshness. Native tests also cover rejection of late successful
   reports, duplicate reports, foreign peers, and same-peer reconnection.
3. AP20 plus session invalidation still allowed 14 startup exchanges at
   compensation 706 before switching to 714, a 12.5 ns calibration step.
   The endpoint could still believe its old association was valid while
   the bridge rebooted. This motivated the additional beacon freshness
   condition tested in the final image.

The disconnect test's first image aborted because its constructor created
an ESP timer before timer initialization. Creating the timer lazily after
Wi-Fi starts fixed the diagnostic. Neither forced-disconnect nor timed-reset
mode is enabled in the final endpoint image.

Aborted status-6 reports contain partial, unclassified RTT fields. The
analyzer now checks driver RTT classification only for statuses 0 and 5,
while retaining raw timestamp and paired conversion checks. Nine Python
regression tests and the native session/freshness tests with UBSan pass.
Both firmware builds succeeded and flashed images passed hash verification.

## Evidence and current firmware

Artifacts are in `build-ftm-startup/`. Earlier isolation windows are
`ap-only-*`; the forced-disconnect capture is `assoc-test-fixed.log`.
`final-*-snapshot.log` and `final-*.json` preserve the initial session guard
capture, including the residual 706 case. The later final image uses
`endpoint-freshness.log`, `freshness-*-snapshot.log`, and `freshness-*.json`.
Responder UART capture remains `build-ftm-paired/responder-console.log`.
The paired analyzer uses exact T1/T4 and dialog tokens, explicitly separates
responder boots, and checks raw-to-converted timestamp consistency.

Running P4 image SHA256:
`f24ccd1e83527433cd20593c8f279b8f12f022b0236d936be9d678c75979440a`.
Running endpoint image SHA256:
`3a8688f90a3aaf7d6355ff93e1f9d6afc106d2dbdc5dce4217f01fcf8cc64ed9`.
Responder image remains:
`eaae2f47695afb42c0573d726224aad3034763a62fb697c0228064e17f0e5c92`.
The host was built before the final STA-only beacon guard; its AP behavior
is current. All changes are uncommitted; the unsigned RTT averaging bug is
still separate and unfixed. No new scope accuracy or audio-load claim is
made by this experiment.

## Final frozen validation window

The final image produced 72 reports over 93.854 seconds, on one endpoint
boot. There were five responder boot segments: the already-running AP,
two explicit identity-verified bridge resets, and two additional resets
caused by attaching its serial logger. One short segment had no matched
FTM data. Across the other four segments, all 977 matched exchanges used
compensation 714. Neither 614 nor 706 appeared in matched data. No roughly
156 ns startup outlier recurred; the total RTT range was -7.813 to +10.937 ns.
There were no queue drops, panics, classified RTT disagreements, endpoint
RX reconstruction errors, responder conversion errors, unmatched available
pairs, ambiguous matches or token mismatches. One status-3 report was
rejected at the association/freshness boundary. Waiting and automatic
recovery were logged after both restart sequences.

Settled medians changed from -4.688 ns before restarts to +7.812 ns in two
segments, then back to -4.688 ns after the repeat. Persistent negative bias
therefore remains, despite removing the observed startup compensation
transition. This limited restart sample does not prove universal elimination.

Ethernet taps were reverified after the final reset: f0 wired endpoint out,
f1 switch toward wired endpoint, f2 bridge out, f3 switch toward bridge.
Live endpoint log is endpoint-freshness.log, P4 log host-freshness-repeat.log,
and the responder console continues unchanged. Forced fault modes are off.
