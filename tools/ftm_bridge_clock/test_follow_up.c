#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include "ftm_follow_up.h"

static const uint8_t upstream[76] = {
    0x18, 2, 0, 76, 3, 0, 0, 8,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xc0, 0,
    0, 0, 0, 0,
    0, 1, 0xf2, 0xff, 0xfe, 0xff, 0x3b, 0x14, 0, 1,
    0x56, 0x78, 2, 0xfd,
    0, 0, 0, 0, 0, 3, 0x3b, 0x9a, 0xc9, 0xff,
    0, 3, 0, 28, 0, 0x80, 0xc2, 0, 0, 1,
    0, 0, 0, 0, 0x12, 0x34,
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    0xff, 0xff, 0xff, 0xfb,
};
static const uint8_t port[10] = {0x80, 0xf1, 0xb2, 0xff, 0xfe, 0xd2, 0xca, 0xa9, 0, 2};

int main(void)
{
    uint8_t result[82], broken[82], template[76];
    ftm_follow_up_fields_t fields;
    assert(ftm_follow_up_relay(upstream, 76, port, 0xabcd, -3, 98304, -512, result));
    const uint8_t expected_prefix[] = {221, 80, 0x00, 0x80, 0xc2, 0};
    const uint8_t expected_correction[] = {0, 0, 0, 0, 0, 1, 0x40, 0};
    const uint8_t expected_rate[] = {0xff, 0xff, 0xfe, 0};
    assert(!memcmp(result, expected_prefix, 6));
    assert(result[7] == 0x12 && result[38] == 0);
    assert(!memcmp(result + 14, expected_correction, 8));
    assert(!memcmp(result + 60, expected_rate, 4));
    assert(!memcmp(result + 26, port, 10));
    assert(result[36] == 0xab && result[37] == 0xcd && result[39] == 0xfd);
    assert(!memcmp(result + 40, upstream + 34, 20));
    assert(!memcmp(result + 64, upstream + 58, 18));
    assert(ftm_follow_up_parse(result, 82, &fields));
    assert(fields.origin_ns == INT64_C(3999999999));
    assert(fields.correction_scaled == 81920 && fields.cumulative_rate_offset == -512);
    assert(fields.sequence == 0xabcd && fields.domain == 3 && fields.log_interval == -3);
    assert(fields.time_base == 0x1234 && !memcmp(fields.source_port, port, 10));
    for (size_t size = 0; size < 82; ++size)
        assert(!ftm_follow_up_parse(result, size, &fields));
    assert(!ftm_follow_up_parse(result, 83, &fields));
    const unsigned corrupt_positions[] = {0, 1, 2, 5, 6, 7, 8, 9, 11, 50, 53, 56};
    for (unsigned index = 0; index < sizeof(corrupt_positions) / sizeof(corrupt_positions[0]); ++index) {
        memcpy(broken, result, 82);
        broken[corrupt_positions[index]] ^= 1;
        assert(!ftm_follow_up_parse(broken, 82, &fields));
    }
    memcpy(template, upstream, 76);
    memset(template + 8, 0xff, 8);
    template[8] = 0x7f;
    assert(!ftm_follow_up_relay(template, 76, port, 0, -3, 1, 0, broken));
    memset(template + 8, 0, 8);
    template[8] = 0x80;
    assert(!ftm_follow_up_relay(template, 76, port, 0, -3, -1, 0, broken));
    assert(ftm_follow_up_relay(template, 76, port, 0, -3, 0, 0, broken));
    assert(ftm_follow_up_parse(broken, 82, &fields) && fields.correction_scaled == INT64_MIN);
    assert(!ftm_follow_up_relay(upstream, 76, port, 0, -3, 0, INT64_MAX, broken));
    memcpy(template, upstream, 76);
    template[43] = 0;
    template[42] = 0xca;
    assert(!ftm_follow_up_relay(template, 76, port, 0, -3, 0, 0, broken));
    memcpy(template, upstream, 76);
    memset(template + 34, 0xff, 6);
    assert(!ftm_follow_up_relay(template, 76, port, 0, -3, 0, 0, broken));
    memset(broken, 0xa5, sizeof(broken));
    assert(!ftm_follow_up_relay(NULL, 0, port, 0, -3, 0, 0, broken));
    for (unsigned index = 0; index < sizeof(broken); ++index) assert(broken[index] == 0xa5);
    puts("FollowUp wire layout, signed fractional correction, metadata and rejection tests pass");
}
