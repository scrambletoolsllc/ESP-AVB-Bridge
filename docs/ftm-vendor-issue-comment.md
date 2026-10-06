# Draft comment for espressif/esp-idf#18689, not posted

Thanks for the vendor IE patches. On d5c60e8c893 with the seven ESP32-C6
libraries they work as agreed: the responder callback runs for every FTM frame
with the previous measurement's t1/t4 and follow-up token, the initiator returns
each IE under that token, and every IE has matched its timestamp entry over
several days of continuous ranging under AVB traffic. Carrying an IEEE
802.1AS-2020 Follow_Up in the IE, we now hold a station clock within about
1 us of the AP's wired gPTP time (oscilloscope, output edges).

Using this as an 802.1AS transport still needs a few things that only the Wi-Fi
library can provide. Clause references are IEEE 802.1AS-2020.

1. Burst request (Table 12-2). The initiator must request one ASAP burst with
   FTMs per burst 3, then 2 on retry. `esp_wifi_ftm_initiate_session` rejects
   `frm_count` 3 and 2 with ESP_ERR_INVALID_ARG; 8 with `burst_period` 0 is the
   smallest accepted and yields one ASAP burst. Please accept small counts, or
   expose Number of Bursts Exponent and ASAP directly.
2. Burst timing (Table 12-3). Burst Duration 10 (64 ms) and Min Delta FTM 100
   (10 ms) are required for the default sync interval. Neither is settable; the
   responder reports `min_delta_ftm` 20.
3. Grant visibility (12.4, 12.5.1.4.2). `wifi_event_ftm_request_t` gives
   `accepted`, saturated `frm_count`, `burst_period` and `min_delta_ftm`. The
   responder needs the granted ASAP flag, bursts exponent, FTMs per burst and
   burst duration, distinguished from the requested values, to set asCapable.
   We see accepted=1, frm_count=8, burst_period=1 for a period 0 request.
4. Reports with nonpositive RTT. At short range the session ends with
   FTM_STATUS_NO_VALID_MSMT and the entries and vendor data are freed before
   `esp_wifi_ftm_get_report` can read them. Time transfer needs the raw t1..t4
   and IEs, not a positive distance; in 802.1AS the MLME indication always
   carries the timestamps and the media layer judges them. Please deliver
   entries and vendor data regardless of the ranging verdict and keep the
   status as is. We are working around this with a hook on the OSI free path,
   which is not something we can ship.
5. Peer capability bits (12.3, Table 12-1). Support is derived from the peer's
   Extended Capabilities FTM responder/initiator bits. The STA has them in
   `wifi_ap_record_t`; the AP has no per-station equivalent. A field in
   `wifi_sta_info_t`, or the bits in the association event, would close this.
   Until then we treat a received FTM Request as evidence of initiator support.
6. Per-peer responder control. With several initiators the AP must stop or
   decline timing for one station while serving the others. Declining in the IE
   callback still sends the full element.
7. Timing Measurement. 12.4 allows TM as the fallback when FTM parameters are
   not granted, and a relay is expected to support it for TM-only stations.
   The ESP32-C6 libraries contain no TM path and the AP beacon's Extended
   Capabilities clear the Timing Measurement bit, so it is unavailable today.
   Is adding it feasible, given the radio already timestamps FTM frames and
   their ACKs?

Items 1, 3 and 4 gate asCapable; 2, 5 and 6 are needed for full conformance.
We can test candidate libraries quickly and share captures from both ends.
