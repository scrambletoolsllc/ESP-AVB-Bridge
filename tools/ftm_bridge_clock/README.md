# Bridge clock and FollowUp checks

From the repository root:

```sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined,address \
  -I components/ftm_bridge_clock/include \
  tools/ftm_bridge_clock/test_bridge_clock.c \
  components/ftm_bridge_clock/ftm_bridge_clock.c -lm \
  -o /tmp/test_bridge_clock && /tmp/test_bridge_clock
cc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined,address \
  -I components/ftm_follow_up/include \
  tools/ftm_bridge_clock/test_follow_up.c \
  components/ftm_follow_up/ftm_follow_up.c \
  -o /tmp/test_follow_up && /tmp/test_follow_up
python3 tools/ftm_bridge_clock/analyze.py path/to/host.log
```

`BRIDGEMAP` columns: result, edge sequence, valid, MAC microseconds,
reference nanoseconds, Q32 rate, read uncertainty nanoseconds, snapshot age
microseconds, prediction residual nanoseconds. INT64_MIN means there was no
valid previous prediction. Status numbers follow `ftm_bridge_result_t`.
Invalid observations reset acquisition; four consecutive valid observations
are needed. `HWRATE` columns: edge sequence, requested trim ppb, applied
Q32 rate, Ethernet addend, subsecond increment, clock selector (0 XTAL,
1 PLL80M). The selector/rate interpretation is for ESP32-P4.

The reference map uses four paired raw hardware edges for oscillator ratio,
then the applied Ethernet rate register for the PTP-to-raw rate. It does not
use RPC arrival as a phase measurement. RPC delay contributes only to age.
Clock generation, boot identity, missing sequence, raw prediction outlier,
MAC discontinuity, wide read bracket and expired snapshot invalidate it.

Read uncertainty is a bracket bound, not end-to-end accuracy. It excludes
fixed skew, Ethernet asymmetry, endpoint mapping error and oscillator change
during holdover. The live prediction check also shares the capture path.
Full FTM payload delivery, endpoint discipline and scope validation remain
separate tests. The FollowUp codec is a task-context reference, not yet safe
for direct use in the radio's IRAM callback.
