# Reply to Sajia (Espressif FTM thread), sent 2026-10-15

Thanks Sajia, that covers most of it. Answers below, then the full list as we understand it, so the requirements can be closed this week.

1 and 2. Thanks. One detail: a responder can also answer Successful while overriding requested parameters (Status Indication 1 of the Fine Timing Measurement Parameters element, Table 9-278 in 802.11-2020). 802.1AS 12.4 counts only a grant of the requested 3 or 2 frames, so please retry with 2 when the response changes the frame count or the other Table 12-2 values, not only when it is declined.

3. Thanks. Please add Min Delta FTM to wifi_event_ftm_report_t as well, since it now follows the sync interval.

6. Neither standard names an allow or deny list. It is how an AP carries out the per station port state that 802.1AS requires:
- 802.1AS-2020 12.1.3: when one 802.11 port is associated with several stations, each association has its own PortSync and MD entity, so each station is a separate PTP Port with its own port state, asCapable and neighborGptpCapable.
- 12.5.1.1: only the MD entity of a port whose state is MasterPort runs the master state machines. In Figure 12-6, master state machine B stays in INITIALIZING, with asCapable FALSE, while the port is not operational or not enabled.

So the AP has to give one station timing and decline another, depending on that station's port:
- MasterPort and enabled: grant, and send FollowUpInformation.
- Just associated, before gPTP capable Signaling and best master selection have run: Request failed (3) with a retry value.
- SlavePort (the station is closer to the grandmaster, so the AP initiates toward it), PassivePort, DisabledPort, or not gPTP capable: Request incapable (2), or failed with a retry value if the state can change.

When the list is set: the gPTP stack on the AP updates a station's entry when that station's port changes: at association (decline with retry), when port state selection assigns MasterPort (allow) or another state (decline or incapable), when the station's gPTP capable TLVs time out, and at disassociation (entry removed). If a port leaves MasterPort during a session, the stack cancels that station's session. These changes come at Announce and Signaling timescales, seconds apart. Because the request event is posted after the response has gone out, the entry has to be in place before the request arrives. If a synchronous decision is easier on your side, a callback when the initial FTM Request arrives, returning allow, incapable, or failed with a Value, works just as well for us.

Clarification 1 (sync interval). A log_sync_interval field in wifi_ftm_initiator_cfg_t with a default of -3 works. 802.1AS lets a station change the interval during an association with a message interval request (12.8.2, 10.3.18), and a per session field covers that. We use -3 today and do not need the rows faster than -5.

Clarification 2 (release). Thanks, v6.2 would be ideal. With the answers here our side of the requirements is complete.

Clarification 3 (RTT offset). Thanks. One note: the three medians came from sessions where the compensation stayed at 714 and 704, so the difference between responder boots comes from something else that is set at boot. A constant offset within ±14 ns is acceptable for 802.1AS link delay, so no change is needed; if you know its source, a short note would help us document it. If it is easy, please also report the compensation value in the report event as well as the log, so we can store it with each measurement. Thanks for the bandwidth change fix.

Clarification 4 (PHY rate). Fine, we will drop it.

The full list as we understand it:
1. ptp_compatible initiator: Number of Bursts Exponent 0, ASAP 1, FTMs per burst 3, retry with 2 when declined or overridden; Burst Duration and Min Delta FTM from Table 12-3 for log_sync_interval (default -3).
2. Granted ASAP, bursts exponent, FTMs per burst, burst duration and Min Delta FTM in wifi_event_ftm_report_t on the initiator, and in the request event on the responder.
3. With a negative average RTT, the report keeps the raw t1 to t4 and the vendor IE entries. We asked for the IE entries in our last reply; please confirm they are included.
4. FTM initiator capability bit in wifi_sta_info_t.
5. Per station responder policy (allow, failed with a Value, incapable) plus cancellation of an active session, or the synchronous callback above.
6. Calibration refreshed on a bandwidth change; the compensation value logged, ideally also reported.
7. FTM only, no Timing Measurement.
