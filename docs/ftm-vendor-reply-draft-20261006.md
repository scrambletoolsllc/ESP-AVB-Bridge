# Draft reply to Nachiket (espressif/esp-idf#18689), 2026-10-06, not posted

Thanks, this plan works for us. A few clarifications and one design question.

1 and 2. The ptp_compatible flag with frm_count 3 or more, burst duration 64 ms and
min delta FTM 10 ms covers the default sync interval. Agreed that N frames give
N minus 1 measurements, and one measurement per burst is enough for 802.1AS, which
needs one Follow_Up per sync interval. The two frame request in Table 12-2 is not
about more measurements, it is the fallback when a responder grants fewer than
three. Against your responder it will not happen, since the grant equals the
request, but against other vendors' responders the initiator must either retry
with two or set asCapable FALSE. Please accept frm_count 2 under ptp_compatible as
well, even though it yields a single measurement. Your internal retry on a missing
response is a separate mechanism and we are happy to rely on it for lost frames.

3. Understood that WIFI_EVENT_FTM_REQUEST reports the granted values on the
responder, and the added ASAP flag, bursts exponent, FTMs per burst and burst
duration will let the AP set asCapable per 12.4. The same determination is made
on the initiator, which must know what the responder granted from the FTM
Response. Please expose the granted parameters on the initiator side too, either
in wifi_ftm_report_entry_t or the report event, or in a session start event.

4. Keeping the report and raw t1 to t4 when the average RTT is negative, under
ptp_compatible, is exactly what we need. Please keep the vendor IE data with it,
since the timing payload is what we lose today. The recalibration fix is welcome,
the backup still matters because the sign of a few ns RTT is noise at short range.

5. An FTM initiator support bit in wifi_sta_info_t is sufficient.

6. Limiting FTM to one peer, or disabling the callback with more than one peer,
would not work for a relay that times several stations. 802.11 already has the
mechanism: the responder answers an FTM Request with an FTM Response whose Status
Indication is Request failed (3, with a retry value) or Request incapable (2).
A per peer policy API, set ahead of time because the request event is
asynchronous, would do it: for a given MAC, allow, decline with a retry value, or
incapable, applied when the FTM Request arrives, plus a way to cancel an active
session for that peer. The zero body IE as a no timing indication is fine as the
interim behaviour, and the initiator already treats it that way.

7. Understood on TIMINGMSMT. We will document that TM only stations are not
served and set asCapable FALSE for them.

We can test a candidate library as soon as it is available and will share captures
from both ends again.
