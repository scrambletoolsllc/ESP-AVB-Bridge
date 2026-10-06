# Wireless capture check, 2026-09-25

The user authorized the spare wireless interface for traffic debugging.
The adapter receives bridge/endpoint data, but the tested monitor paths do
not provide usable FTM action frames. Missing FTM in these captures is not
evidence that the boards failed to exchange FTM.

Adapter: `wlx7419f816a466`, MAC `74:19:f8:16:a4:66`, phy3, USB MediaTek
`0e8d:7961`, driver `mt7921u`, kernel `6.17.2-1-pve`, firmware
`____010000-20250625153703`. It was initially down and unassociated. Host
connectivity uses Ethernet; no Wi-Fi association or packet injection was
performed. Capture used only dumpcap/tshark.

Channel 6 / HT20 matches the endpoint association log and passive scan.
The scan identifies bridge BSSID `d8:85:ac:fa:2c:59`, SSID
`ESP-AVB-Bridge`, about -25 dBm, and its advertised FTM-responder capability.

Tested separate and original monitor interfaces, unfiltered capture,
control/otherbss/FCS-fail flags, the supported active-monitor flag, a live
unassociated managed interface, monitor reopen, and passive scan windows.
Most received valid frames were 1 Mb/s data frames. Ordinary monitor
captures omitted beacons as well as FTM. Each passive-scan capture exposed
one beacon. No action codes were decoded in any capture. A few other
apparent subtypes were flagged bad-FCS and are not protocol evidence.

This narrows the limitation to the receive/capture path, but does not
establish a specific driver or firmware root cause. Do not derive FTM
loss, negotiation parameters, timing precision or conformance from it.
Data captures can still support AVB forwarding investigation.

Artifacts: `build-ftm-discipline/ftm-air-*.pcapng`, capture logs,
`ftm-air-summary.json`, `passive-scan.txt`, `passive-scan-long.txt`.
The temporary `monftm` interface was removed and the original interface
restored to managed/down. Firmware on the bridge and endpoints was not
changed during this wireless capture experiment.
