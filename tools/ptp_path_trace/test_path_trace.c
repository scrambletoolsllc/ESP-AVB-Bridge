#include <assert.h>
#include <stdio.h>
#include "ptp_path_trace.h"

int main(void) {
  uint8_t packet[256] = {0};
  uint8_t local[8] = {0x80, 0xf1, 0xb2, 0xff, 0xfe, 0xd2, 0xca, 0xa9};
  uint8_t receiver[8] = {0xfc, 1, 0x2c, 0xff, 0xfe, 0xfd, 0xfe, 0x80};
  ptp_path_trace_t upstream = {.count = 2,
    .identities = {{0, 1, 0xf2, 0xff, 0xfe, 0xff, 0x3b, 0x14}, {1, 2, 3, 4, 5, 6, 7, 8}}};
  size_t tlv_length = ptp_path_trace_write(packet + 64, sizeof(packet) - 64, &upstream, local);
  assert(tlv_length == 28);
  packet[3] = 64 + tlv_length;
  ptp_path_trace_t parsed = {0};
  assert(ptp_path_trace_parse(packet, sizeof(packet), receiver, &parsed));
  assert(parsed.count == 3 && !memcmp(parsed.identities, upstream.identities, 16));
  assert(!memcmp(parsed.identities[2], local, 8));
  assert(!ptp_path_trace_parse(packet, sizeof(packet), local, &parsed));
  for (size_t length = 0; length < packet[3]; ++length)
    assert(!ptp_path_trace_parse(packet, length, receiver, &parsed));
  packet[67] = 23;
  assert(!ptp_path_trace_parse(packet, sizeof(packet), receiver, &parsed));
  packet[67] = 24;
  memcpy(packet + 92, packet + 64, 28);
  packet[3] = 120;
  assert(!ptp_path_trace_parse(packet, sizeof(packet), receiver, &parsed));
  packet[93] = 9; /* Unknown, well-formed TLV after path trace. */
  assert(ptp_path_trace_parse(packet, sizeof(packet), receiver, &parsed));
  packet[3] = 64;
  assert(ptp_path_trace_parse(packet, sizeof(packet), receiver, &parsed) && !parsed.count);
  for (unsigned count = 0; count < PTP_PATH_TRACE_MAX_CLOCKS; ++count) {
    upstream.count = count;
    for (unsigned index = 0; index < count; ++index)
      memset(upstream.identities[index], index + 1, 8);
    tlv_length = ptp_path_trace_write(packet + 64, sizeof(packet) - 64, &upstream, local);
    assert(tlv_length == 4 + (count + 1) * 8);
    packet[2] = (64 + tlv_length) >> 8;
    packet[3] = 64 + tlv_length;
    assert(ptp_path_trace_parse(packet, sizeof(packet), receiver, &parsed));
    assert(parsed.count == count + 1);
    assert(!ptp_path_trace_write(packet + 64, tlv_length - 1, &upstream, local));
  }
  upstream.count = PTP_PATH_TRACE_MAX_CLOCKS;
  assert(!ptp_path_trace_write(packet + 64, sizeof(packet) - 64, &upstream, local));
  upstream.count = 1;
  memcpy(upstream.identities[0], local, 8);
  assert(!ptp_path_trace_write(packet + 64, sizeof(packet) - 64, &upstream, local));
  puts("Path trace chain, loop, truncation, duplicate TLV and capacity tests passed");
}
