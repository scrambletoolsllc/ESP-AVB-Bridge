# ESP-Hosted synchronous RPC failures during FTM testing

The loaded bridge rebooted twice while the PTP publisher and diagnostic
clock-mapping tasks issued concurrent synchronous RPCs:

- 2026-09-25 07:50 UTC: station-list wrapper dereferenced a NULL response
  after a failed response-slot lookup. Decoded PC points to
  `rpc_wifi_ap_get_sta_list`, the count assignment outside its success guard.
- 08:00 UTC: `hosted_destroy_semaphore` asserted on a NULL handle while
  cleaning up a synchronous custom-data request.

The first fault is guarded by
`patches/esp-hosted-station-list-null-response.patch`. It retains the
original error return and reports zero stations on failure.

The underlying synchronous RPC design had three concurrency problems:
UID allocation was unprotected; callers could claim or retire the same
response-table slot concurrently; responses shared a FIFO even though
semaphores woke callers by UID. The FIFO could therefore deliver another
caller's response when callers resumed in a different order.

`patches/esp-hosted-concurrent-sync-rpc.patch` stores the response in its
request's slot. A short ESP FreeRTOS critical section protects UID
allocation, slot publication, response delivery and slot retirement. The
requester waits outside the critical section, detaches the slot, and then
deletes its semaphore. Late and duplicate replies fail lookup and are
rejected. Local transmit-failure replies now carry the request UID too.
The former shared response FIFO is removed.

The patch preserves concurrent synchronous requests; it does not serialize
all callers behind a blocking transaction mutex. It does not redesign the
separate asynchronous callback table or concurrent library shutdown. Those
paths require their own audit before making a general SDK-wide assurance
claim.

Native verification compiles the installed source functions with a pthread
critical section and semaphore implementation:

```sh
python3 tools/hosted_rpc/test_station_list.py
python3 tools/hosted_rpc/test_sync_routing.py
```

The tests cover NULL/error/success station-list replies, reverse-order
responses, 40,000 concurrent calls, duplicates, late replies and 1,000
reply/timeout retirement races. ASan/UBSan passed. P4 firmware built and
flashed with hash verification. Longer loaded hardware validation is
recorded in `project.md` and `build-ftm-discipline/host-ftm-rpc-routing-live.log`.

These managed-component edits are also stored as patches because managed
dependencies are ignored by Git. No vendor message has been sent.
