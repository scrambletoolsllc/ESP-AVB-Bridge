# Local ESP-Hosted fixes

`esp-hosted-station-list-null-response.patch` fixes a NULL dereference in
`rpc_wifi_ap_get_sta_list` when a synchronous RPC has no response. The
wrapper already guards the station array copy, but copied the count
outside that guard. A failed query now returns zero stations and retains
the original RPC error return.

Observed on the loaded bridge on 2026-09-25 at 07:50 UTC, in the Announce
publisher task. The missing RPC response itself remains under investigation.

Apply from the repository root after installing managed dependencies:

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-station-list-null-response.patch
python3 tools/hosted_rpc/test_station_list.py
```

The regression test compiles the actual installed wrapper with stubbed RPC
responses and ASan/UBSan. Managed dependencies are ignored by Git; retain
this patch when regenerating them.

`esp-hosted-concurrent-sync-rpc.patch` replaces the shared synchronous
response FIFO with a response slot keyed by request UID. UID allocation,
slot publication, reply delivery and retirement use a short critical
section. Waiting and memory allocation/deletion happen outside it. This
prevents concurrent callers from claiming the same slot or consuming each
other's reply. Late/duplicate replies are rejected, and transmit-failure
responses retain the originating UID.

The loaded bridge had both an unmatched station-list response and a NULL
semaphore deletion assertion. The slot helpers pass native tests with
reverse-order replies, 40,000 concurrent requests and 1,000 timeout/reply
races under ASan/UBSan. Hardware validation is recorded in project.md.
This patch targets the ESP FreeRTOS host; it does not redesign the separate
asynchronous callback table or concurrent RPC-library shutdown.

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-concurrent-sync-rpc.patch
python3 tools/hosted_rpc/test_sync_routing.py
```

`esp-hosted-bounded-data-tx.patch` makes AP/STA SDIO data queue insertion
nonblocking. A full queue returns `ESP_ERR_NO_MEM` and releases the supplied
transport buffer once; only successful insertion wakes the transmitter.
Control/RPC traffic retains its wait policy, with failed insertion now handled.
This prevents a synchronous network RX caller from waiting indefinitely for
radio queue capacity. It does not guarantee lossless audio or reserve bandwidth
for Signaling. Queue saturation remains an explicit data loss condition.

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-bounded-data-tx.patch
python3 tools/hosted_rpc/test_data_tx.py
```

The test compiles the installed SDIO function and release macro, checks both
buffer modes, ownership, failures, priorities and control timeout policy under
ASan/UBSan. Hardware results are recorded in project.md.

`esp-hosted-ap-event-mac.patch` replaces `strlen` on the six-byte binary
station MAC in AP association/disassociation event forwarding. The bounded
check accepts valid zero-leading MACs and does not read past the address.
All-zero placeholders remain ignored.

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-ap-event-mac.patch
python3 tools/hosted_rpc/test_ap_event_mac.py
```

`esp-hosted-association-lifecycle.patch` applies to the separate
`esp-hosted-mcu` coprocessor tree. It returns the actual enqueue result from
`send_event_data_to_host` and adds optional begin/complete hooks around AP
join, leave and stop notification forwarding. The FTM component uses these
hooks to retire snapshots before enqueue and track whether the notification
was accepted. A successful enqueue is not proof of host event processing.

```sh
patch -d ../esp-hosted-mcu -p1 < patches/esp-hosted-association-lifecycle.patch
python3 tools/ftm_association/test_lifecycle_hook.py
```

This patch is built but not yet deployed; host admission and map transport
integration remain necessary before using its generation to authorize FTM.
