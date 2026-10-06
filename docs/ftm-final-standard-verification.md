# Verification against IEEE Std 802.1AS-2020 and Cor 1-2021

Verified 2026-09-25 against the final text in `Documents/Standards/8021AS-2020.pdf`
and `8021AS-2020_Cor1-2021.pdf`. Earlier checks used the public 2019 D8 draft;
the items below supersede them. "Fixed" means the working tree now matches the
clause and the native tests cover the change. "SDK" means the requirement cannot
be met through the ESP-IDF FTM API installed on this bench and is recorded in
`ftm-vendor-followup-draft.md`. No conformance claim is made for the path as a
whole while any SDK item remains.

## Clause 12, IEEE 802.11 links

| Clause | Requirement | Implementation | Result |
| --- | --- | --- | --- |
| 12.1.2.2, 12.6 Table 12-2 | Slave requests one burst (Number of Bursts Exponent 0), ASAP 1, three FTMs per burst, then two if not granted, then TM or asCapable FALSE | `ptp_wifi.c` requests 3, then 2, then falls back to 8 only to keep the experimental path alive | SDK: `esp_wifi_ftm_initiate_session` rejects 3 and 2 with `ESP_ERR_INVALID_ARG`; no ASAP or burst-exponent control |
| 12.6 Table 12-3 | For log interval -3: Burst Duration 10 (64 ms), Min Delta FTM 100 (10 ms) | Not settable | SDK: request event reports burst period 1 and min delta 20 (2 ms) |
| 12.1.2.2 | Slave uses the minimum-delay pair of the first two FTM frames | Minimum-RTT quartet, optionally independent forward/reverse minima, over the eight-frame fallback burst | Equivalent method over a non-conformant burst; "other methods can be used" (12.5.2.4.4) |
| 12.2 | Announce and Signaling unicast to the station address | `ptp_wifi_ap_send_announce`, `wifi_capable_send_to` | Conformant |
| 12.3 Table 12-1 | tmFtmSupport from local support and the peer's Extended Capabilities | `ptp_wifi_capable.h`, STA reads `wifi_ap_record_t.ftm_responder` | Fixed on the STA port. The AP port has no per-station Extended Capabilities in `wifi_sta_info_t`, so its bit stays unknown |
| 12.4 | asCapable requires tmFtmSupport, neighborGptpCapable and TM or a three/two-frame grant | `ptp_wifi_capability()` in `ptp.c`; `GET_AVB_INFO.asCapable` now reports it on the endpoint | Fixed logic; evaluates FALSE on this bench because no small burst is ever granted |
| 12.5.1.4.1 b) | VendorSpecific IE: Element ID 221, Length 80, OUI or CID 00-80-C2, Type 0 | `ftm_follow_up.c` prefix | Fixed: the prefix previously carried 8C-1F-64 |
| 12.5.1.4.6 | correctionField = rateRatio × (t1 − upstreamTxTime) + upstream correctionField, with the previous measurement's t1 | `ftm_follow_up_emit` applies `(departure − anchor) × rate` to the relayed correction; the callback receives the previous measurement's t1 | Conformant |
| 12.7 | FollowUpInformation carries the entire Follow_Up: header, preciseOriginTimestamp, Follow_Up information TLV | 76-octet Follow_Up inside the 82-octet IE, TLV 0x0003/28/00-80-C2/1 | Conformant |
| 11.4.2.8, 10.5.7 | Follow_Up sequenceId is the transmitting port's own sequence; the FTM dialog tokens pair the IE with its measurement | Responder keeps one sequence pool per logical port; the endpoint pairs by driver dialog token only | Fixed: the responder previously wrote the follow-up dialog token into sequenceId and the endpoint required equality |
| 12.5.1.3.10, 12.5.1.2 | nframesSent, burst duration and grant handling in the master | Driver-owned | SDK: no grant decision or burst control is exposed |
| 12.5.2.4.4 | neighborRateRatio and meanLinkDelay from consecutive indications | Fitted over the first and last paired quartets of the burst; RTT per quartet with the neighbor rate applied to the turnaround | Conformant method |
| 12.8.2 | Default log sync interval -3; 127 stops, 126 resets, -128 unchanged; logLinkDelayInterval -128 by sender, ignored by receiver; unsupported logTimeSyncInterval ignored | `ptp_sync_interval.h`, `ptp_signaling.h` | Conformant. Only -3 and stop are supported, which the clause permits |
| 12.1.3 | One PortSync and MD instance per association | Logical port identities, per-association Announce, capability and stop/reset policy | Partial: per-association PortSync/MD state machines remain open, see `ftm-current-status.md` |

## Clause 10 media-independent items used on this path

| Clause | Requirement | Implementation | Result |
| --- | --- | --- | --- |
| 10.6.2.2.3, .13, .14 | minorVersionPTP 1, controlField 0, Signaling logMessageInterval 0x7F | `ptp_signaling_write_capable`, relay templates | Conformant |
| 10.6.4.2.1 | Signaling targetPortIdentity all ones | Writer sets 0xFF × 10; receiver accepts all ones or its own identity | Conformant |
| 10.6.4.3 | Message interval request TLV: tlvType 0x0003, length 12, subtype 2 | `ptp_signaling_read_message_interval` | Conformant |
| 10.6.4.4 | gPTP-capable TLV: tlvType 0x8000, length 12, subtype 4, flags FALSE, reserved 0 | `ptp_signaling_write_capable` | Fixed: tlvType was 0x0003 |
| 10.6.4.5 | gPTP-capable message interval request TLV: tlvType 0x8000, length 10, subtype 5 | `ptp_signaling_write_capable_interval` | Fixed: tlvType was 0x0003 |
| 10.7.2.5 | gPTP-capable interval default 0, range -24..24 | Default 0, supported -3..24 | Conformant |
| 10.4.3.2.2 | Unsupported faster gPTP-capable rates select the closest longer supported interval | `ptp_capable_interval_request` maps -24..-4 to -3; reserved values are ignored | Fixed: such requests were ignored |
| 10.7.3.3, 10.4.2 | gPtpCapableReceiptTimeout 9 intervals | `ptp_capable_receive.h` | Conformant |
| Cor 1, 10.2.5.19 and Figure 10-23 | Slowdown when the new interval is longer; send gPtpCapableReceiptTimeout messages at the old rate first | `ptp_capable_interval.h` (9 messages) | Conformant |
| Cor 1, 10.3.10.2 and Figure 10-19 | Announce slowdown when the new interval is longer; announceReceiptTimeout messages at the old rate | `ptp_announce_schedule.h` (3 messages) | Conformant |
| 10.7.3.1, 10.7.3.2 | syncReceiptTimeout 3, announceReceiptTimeout 3 | `ptp_sync_receipt.h`, `ptp_announce_receipt_timeout_ns` | Conformant |
| 10.6.3.3 | Path trace TLV appended and loop-checked; absent TLV accepted | `ptp_path_trace.h` | Conformant |

## Clause 11 items on the bridge's wired port

| Clause | Requirement | Implementation | Result |
| --- | --- | --- | --- |
| 11.2.2 a)-d) | asCapableAcrossDomains from peer-delay exchange, meanLinkDelayThresh, single responder, no self response | `ptp_peer_exchange.h`, `ptp_peer_capability.h` | Conformant, with a conservative three-interval freshness guard |
| 11.2.2 e)-f) | asCapable additionally needs neighborGptpCapable or domain 0 with sdoId 0x100 | `ptp_peer_capable()` | Conformant |
| Cor 1, Figure 11-9 | Lost responses counted after the interval timer; neighborRateRatio used in delay | `ptp_peer_rate.h`, loss accounting | Conformant |
| Table 10-9 | Pdelay_Resp twoStepFlag ignored on reception | Receiver | Conformant |

## Files changed for the fixed items

- `components/ftm_follow_up/ftm_follow_up.c`: 00-80-C2 prefix.
- `components/ftm_follow_up/ftm_follow_up_tx.c`, `ftm_follow_up_tx.h`: sequenceId parameter.
- `components/ftm_clock_probe/ftm_clock_probe.c`: per-port sequence pools in the responder callback.
- `components/ftm_endpoint/ftm_endpoint.c`: pairing by dialog token only.
- `esp_ptp/ptp_signaling.h`: 0x8000 for subtypes 4 and 5 on transmit and receive.
- `esp_ptp/ptp_capable_interval.h`: closest-longer mapping.
- `esp_ptp/ptp_wifi_capable.h`, `ptp_wifi.c`, `ptp.c`, `ptp.h`: 12.3/12.4 determination and status.
- Bench senders and analyzers under `tools/` follow the new TLV types.

Both ends of the wireless link must run the updated images together: the IE
prefix and the Signaling TLV types changed on the wire.
