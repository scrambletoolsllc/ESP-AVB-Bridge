# SDK capability questions, draft only

Related issue: https://github.com/espressif/esp-idf/issues/18689

This has not been posted or sent. It records the remaining SDK questions
separately from the application's clock-mapping and servo work.

The vendor IE patches are installed on ESP32-C6, using the local IDF tree
based on `d5c60e8c893`. Captures from both ends confirm delivery of matching
FTM timestamps. We still need clarification on these capabilities:

1. How should the application request a single ASAP burst with an explicit
   small frame count, minimum FTM spacing and burst duration? IEEE Std
   802.1AS-2020 Table 12-2 requires Number of Bursts Exponent 0, ASAP 1, FTMs
   per burst 3 (then 2 on retry), and Table 12-3 requires, for the default
   log sync interval -3, Burst Duration 10 (64 ms) and Min Delta FTM 100
   (10 ms); the initiator must retry with two frames if three are not granted
   and set asCapable FALSE if neither is granted (12.1.2.2, 12.4). The installed
   `wifi_ftm_initiator_cfg_t` exposes frame counts 0/16/24/32/64 and a burst
   period in 100 ms units. Explicit three-frame and two-frame requests both return
   ESP_ERR_INVALID_ARG (sequential boot test at08:52UTC,2026-09-25). Eight frames, period zero is accepted and logs one
   ASAP burst of eight, duration32ms. Sixteen frames, period zero still
   negotiates two non-ASAP bursts of eight. These controls do not appear sufficient for the desired
   802.1AS transport negotiation. Please identify an existing supported API,
   or provide the necessary initiator/responder configuration extension and
   matching libraries. We will verify actual requested/granted parameters on
   the wire, including fallback/retry behavior.
2. Can the application receive valid raw timestamp quartets and their
   matching vendor IEs even when every derived RTT is non-positive? On this
   bench the driver can report failure status 5 and discard the report
   buffer in that case. Diagnostic capture before disposal recovers raw
   entries. Clock-transfer validity needs to be evaluated independently of
   the driver's positive-distance filter; we do not want to fabricate a
   positive RTT or ship a private-buffer hook.

3. Does ESP32-C6 expose the legacy IEEE 802.11 TIMINGMSMT service as well
   as FINETIMINGMSMT, for both applicable timing roles? Public
   P802.1AS-Rev/D8.0 clause 5.6 requires TM support for a PTP Relay Instance
   to interoperate with TM-only stations; FTM support is recommended there.
   This needs confirmation against the final 2020 edition. The application
   currently implements only FTM, and a search of the installed public Wi-Fi
   headers did not identify a TM API. That is not proof of hardware or library
   incapability. Please identify supported APIs and any required library changes.

For the second item, useful contract details include which entries remain
valid, per-entry error flags, token association, ownership/lifetime of
returned data and whether failure events may still carry timestamp data.
Please also clarify whether any relevant calibration or timestamp validity
changes require a new Wi-Fi library.

Application-side upstream FollowUp propagation, coherent hardware-domain
mappings and an FTM-only endpoint servo are now operating experimentally.
A hash-gated diagnostic preserved both discarded arrays without modifying
timestamps or driver status. Signed rate-corrected RTTs remain a few ns
below zero in some RF states. Independent scope output-edge measurements
include a loaded 599/599 measurable paired run within1us over11m26s
(maximum absolute offset991ns, absolute p95648ns; one additional acquisition
preceded the first endpoint pulse); these are not a conformance claim.
We need supported APIs instead of the private retention hook. Full burst,
Signaling and final standard-edition checks remain application acceptance
work, tracked in `ftm-conformance-gaps.md`.

Grant notification clarification: the supplied `wifi_event_ftm_request_t` reports
`accepted`, total `frm_count` (saturated at 255), `burst_period`, and `min_delta_ftm`.
Please expose or document supported access to the actual granted ASAP flag, number
of bursts exponent, FTMs per burst and burst duration, distinguishing requested
values from granted values. Total frame count and acceptance alone cannot establish
that the required single ASAP burst with two or three frames was granted. The
asynchronous event is suitable for bookkeeping; we are not asking it to approve a
request retroactively. Please also identify how to read the peer's advertised TM/FTM
capability bits on the AP side for each association.

Live responder observation, 2026-09-25: accepted=1, frm_count=8,
burst_period=1 (100 ms), min_delta_ftm=20 (2 ms). The initiator requests period
zero and logs one ASAP burst. Please clarify requested-versus-granted semantics
and period normalization. This event does not expose the other grant fields above.

Per-peer responder timing control: the callback documentation states that declining
an IE still transmits its full registered length. Which supported API allows the
application to stop timing transmission or refuse future timing requests for one
association while other associations continue? The asynchronous request event is
not an admission decision. Clearing our Follow_Up payload is insufficient evidence
of native FTM stop behavior. Please distinguish whole-frame cancellation, IE
omission, burst rejection and cancellation of an already active exchange.
