# Reply to Nachiket (espressif/esp-idf#18689), draft 2026-10-07, not posted

Thanks, this plan works for us. A few clarifications and one design question.

1 and 2. The ptp_compatible flag with frm_count 3, burst duration 64 ms and
min delta FTM 10 ms covers the default sync interval. Agreed that N frames
give N minus 1 measurements, and one measurement per burst is enough for
802.1AS. The two frame request in Table 12-2 is not about measurement count,
it is the fallback when a responder grants fewer than three frames. That will
not happen against your responder, but it will against other vendors', and
the initiator must then retry with two or set asCapable FALSE. Please accept
frm_count 2 under ptp_compatible as well.

3. Understood that the request event reports the granted values on the
responder, and the added ASAP flag, bursts exponent, FTMs per burst and burst
duration will let the AP set asCapable. The initiator makes the same decision
from the FTM Response, so please expose the granted parameters on the
initiator side too, in the report event or a session start event.

4. Keeping the report and raw t1 to t4 when the average RTT is negative is
exactly what we need. Please keep the vendor IE entries with it as well: the
Follow_Up we transfer rides in them, and today they are freed together with
the report.

5. An FTM initiator support bit in wifi_sta_info_t is sufficient.

6. Limiting FTM to one peer, or disabling the callback with more than one
peer, does not work for a relay timing several stations. 802.11 already has
the mechanism: the responder answers an FTM Request with an FTM Response whose
Status Indication is Request failed (3, with a retry value) or Request
incapable (2). A per peer policy set ahead of time, since the request event is
asynchronous, would do it: allow, decline with a retry value, or incapable for
a given MAC, applied when the request arrives, plus cancellation of an active
session for that peer. The zero body IE as a no timing indication is fine in
the meantime.

7. Understood on TIMINGMSMT. We will document FTM only and set asCapable FALSE
for TM only stations.

We can test a candidate library as soon as it is available and share captures
from both ends.
