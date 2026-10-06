#include "ftm_follow_up.h"
#include <limits.h>
#include <string.h>

static uint64_t read_be(const uint8_t *bytes, unsigned count)
{
    uint64_t result = 0;
    for (unsigned index = 0; index < count; ++index)
        result = (result << 8) | bytes[index];
    return result;
}

static void write_be(uint8_t *bytes, uint64_t value, unsigned count)
{
    while (count) {
        bytes[--count] = value;
        value >>= 8;
    }
}

static int64_t signed_scaled(uint64_t value)
{
    return value <= INT64_MAX ? (int64_t)value : -1 - (int64_t)(UINT64_MAX - value);
}

static bool decode(const uint8_t *message, size_t size, ftm_follow_up_fields_t *fields)
{
    static const uint8_t tlv_prefix[10] = {0, 3, 0, 28, 0, 0x80, 0xc2, 0, 0, 1};
    if (!message || size != FTM_FOLLOW_UP_SIZE || message[0] != 0x18 ||
        (message[1] & 15) != 2 || read_be(message + 2, 2) != FTM_FOLLOW_UP_SIZE ||
        message[5] != 0 || memcmp(message + 44, tlv_prefix, sizeof(tlv_prefix)))
        return false;
    uint64_t seconds = read_be(message + 34, 6);
    uint64_t nanoseconds = read_be(message + 40, 4);
    if (nanoseconds >= 1000000000 || seconds > (INT64_MAX - nanoseconds) / 1000000000)
        return false;
    uint32_t rate_bits = read_be(message + 54, 4);
    *fields = (ftm_follow_up_fields_t){
        .origin_ns = (int64_t)(seconds * 1000000000 + nanoseconds),
        .correction_scaled = signed_scaled(read_be(message + 8, 8)),
        .cumulative_rate_offset = rate_bits <= INT32_MAX ? (int32_t)rate_bits
            : -1 - (int32_t)(UINT32_MAX - rate_bits),
        .sequence = read_be(message + 30, 2), .time_base = read_be(message + 58, 2),
        .domain = message[4],
        .log_interval = message[33] <= INT8_MAX ? (int8_t)message[33]
            : -1 - (int8_t)(UINT8_MAX - message[33]),
    };
    memcpy(fields->source_port, message + 20, 10);
    return true;
}

bool ftm_follow_up_parse(const uint8_t *ie, size_t size, ftm_follow_up_fields_t *fields)
{
    static const uint8_t prefix[6] = {221, 80, 0x00, 0x80, 0xc2, 0};
    if (!ie || !fields || size != FTM_FOLLOW_UP_IE_SIZE || memcmp(ie, prefix, 6))
        return false;
    return decode(ie + 6, FTM_FOLLOW_UP_SIZE, fields);
}

bool ftm_follow_up_relay(const uint8_t *upstream, size_t size,
    const uint8_t source_port[10], uint16_t sequence, int8_t log_interval,
    int64_t additional_correction_scaled, int64_t cumulative_rate_offset,
    uint8_t output[FTM_FOLLOW_UP_IE_SIZE])
{
    ftm_follow_up_fields_t parsed;
    if (!output || !source_port || !decode(upstream, size, &parsed) ||
        cumulative_rate_offset < INT32_MIN || cumulative_rate_offset > INT32_MAX ||
        (source_port[8] == 0 && source_port[9] == 0)) return false;
    if ((additional_correction_scaled > 0 &&
         parsed.correction_scaled > INT64_MAX - additional_correction_scaled) ||
        (additional_correction_scaled < 0 &&
         parsed.correction_scaled < INT64_MIN - additional_correction_scaled)) return false;
    uint8_t result[FTM_FOLLOW_UP_IE_SIZE] = {221, 80, 0x00, 0x80, 0xc2, 0};
    uint8_t *message = result + 6;
    memcpy(message, upstream, FTM_FOLLOW_UP_SIZE);
    write_be(message + 8, (uint64_t)(parsed.correction_scaled + additional_correction_scaled), 8);
    memcpy(message + 20, source_port, 10);
    write_be(message + 30, sequence, 2);
    message[1] = 0x12;
    message[5] = 0;
    memset(message + 16, 0, 4);
    message[32] = 0;
    message[33] = (uint8_t)log_interval;
    write_be(message + 54, (uint32_t)cumulative_rate_offset, 4);
    memcpy(output, result, sizeof(result));
    return true;
}
