# Local ESP-Hosted fixes

The host (`main/`) and the coprocessor (`coprocessor/`) both build on the
`espressif/esp_hosted` 3.0.9 component. Three patches apply to the host's
copy in `managed_components/espressif__esp_hosted`, in the order below,
and one to the coprocessor's copy in
`coprocessor/managed_components/espressif__esp_hosted`. Managed
dependencies are ignored by Git; reapply these patches when regenerating
them.

The 2.x patches for the station list NULL response, concurrent
synchronous RPC, the AP event MAC, the SDIO receive wait, SDIO transmit
coalescing and the association lifecycle hooks are gone: 3.x fixes the
first four, aggregates SDIO frames in both directions itself, and
esp_hosted_avb follows associations through the 3.x coprocessor's Wi-Fi
events.

`esp-hosted-thread-placement-queue-space.patch` adds two host-side hooks
for a bridge that forwards a stream. A weak `hosted_thread_placement`
lets the application set each hosted thread's priority and core by name,
and `esp_hosted_data_tx_queue_space` reports the free entries in the data
queue to the coprocessor. Unpinned, the SDIO threads preempted `emac_rx`
on its own core at every hand-off, and an 8000 frame/s Class B stream
overflowed the EMAC RX ring and cost the bridge gPTP, MSRP and the beacon
refresh. The bridge moves the hosted threads to core 1, runs `sdio_read`
below `sdio_rx_buf` and `sdio_process_rx`, gives the RPC threads back the
priority they had in 2.x, and keeps four queue entries for control
frames.

The patch also fixes a write after free in `eh_host_port_task_create`.
The task handle was stored through the task's own wrapper, which a
detached task frees when it returns, and with PSRAM stacks the create
call stores the handle only after the new task has run. Once
`sdio_process_rx` ran below the default priority, the `eh_auto_init` task
it spawns finished first on every boot, and the handle write corrupted
the heap.

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-thread-placement-queue-space.patch
```

`esp-hosted-bounded-data-tx.patch` makes AP/STA SDIO data queue insertion
nonblocking. A full queue returns `ESP_ERR_NO_MEM`, which the transport
channel now passes up instead of `ESP_FAIL`, and releases the transport
buffer once. Control/RPC traffic keeps its wait. This prevents a
synchronous network RX caller from waiting indefinitely for radio queue
capacity, and esp_avb counts the refused frames as backpressure drops.

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-bounded-data-tx.patch
python3 tools/hosted_rpc/test_data_tx.py
```

`esp-hosted-peer-data-event-loss.patch` frees a received peer data
message that the default event loop refused. 3.x posts each one to that
loop without waiting and leaked the copy when the queue was full; the
patch also counts the loss, which costs esp_hosted_avb and the FTM probe
a message.

```sh
patch -d managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-peer-data-event-loss.patch
```

`esp-hosted-bounded-data-rx.patch` applies to the coprocessor. The AP's
receive callback runs on the coprocessor's Wi-Fi task and hands each frame
to `sdio_write`, which waited without limit for room in the queue to the
host. Once a station's uplink outran the host, the Wi-Fi task blocked and
the AP stopped beaconing. A data frame that finds the queue full is now
dropped and counted, with a summary at most every 10 s; control and
events have their own queues in 3.x.

```sh
patch -d coprocessor/managed_components/espressif__esp_hosted -p1 < patches/esp-hosted-bounded-data-rx.patch
```
