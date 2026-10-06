#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_peers.h"

int main(void)
{
    ptp_capable_schedule_t state = {0};
    uint32_t token = ptp_capable_schedule_begin(&state, true, 0);
    assert(token && state.sequence == 1);
    assert(!ptp_capable_schedule_begin(&state, true, 125000));
    assert(!ptp_capable_schedule_finish(&state, token + 1, true, 100));
    assert(ptp_capable_schedule_finish(&state, token, true, 100));
    assert(!ptp_capable_schedule_finish(&state, token, true, 200));
    assert(!ptp_capable_schedule_begin(&state, true, 999999));
    token = ptp_capable_schedule_begin(&state, true, 1000000);
    assert(token && state.sequence == 2);
    uint32_t expired = token;
    token = ptp_capable_schedule_begin(&state, true, 2000000);
    assert(token && token != expired);
    assert(!ptp_capable_schedule_finish(&state, expired, true, 2000001));
    assert(ptp_capable_schedule_finish(&state, token, false, 2000001));
    assert(ptp_capable_schedule_request(&state, 2));
    int64_t now_us = 2100000;
    for (unsigned index = 0; index < 9; ++index) {
        token = ptp_capable_schedule_begin(&state, true, now_us);
        assert(token && state.advertised_interval == 2);
        assert(ptp_capable_schedule_finish(&state, token, true, now_us + 10));
        assert(state.interval.slowdown_remaining == 8 - index);
        now_us += 1000000;
    }
    assert(!ptp_capable_schedule_begin(&state, true, now_us));
    now_us += 3000010;
    token = ptp_capable_schedule_begin(&state, true, now_us);
    assert(token);
    assert(ptp_capable_schedule_request(&state, -3));
    assert(ptp_capable_schedule_request(&state, 2));
    assert(!ptp_capable_schedule_finish(&state, token, true, now_us + 1));
    assert(state.interval.slowdown_remaining == 9);
    token = ptp_capable_schedule_begin(&state, true, now_us);
    assert(token);
    assert(ptp_capable_schedule_request(&state, 2));
    assert(ptp_capable_schedule_finish(&state, token, true, now_us + 1));
    assert(state.interval.slowdown_remaining == 8);
    assert(ptp_capable_schedule_request(&state, 127));
    assert(!ptp_capable_schedule_begin(&state, true, now_us + 10000000));
    assert(ptp_capable_schedule_request(&state, 126));
    token = ptp_capable_schedule_begin(&state, true, now_us);
    assert(token);
    assert(!ptp_capable_schedule_begin(&state, false, now_us));
    assert(!ptp_capable_schedule_finish(&state, token, true, now_us + 1));
    token = ptp_capable_schedule_begin(&state, true, now_us);
    assert(token);
    assert(!ptp_capable_schedule_finish(&state, token, true, now_us - 1));
    token = ptp_capable_schedule_begin(&state, true, now_us + 2000000);
    assert(token);
    assert(!ptp_capable_schedule_finish(&state, token, true, now_us + 3000000));
    assert(!ptp_capable_schedule_begin(&state, true, -1));
    assert(!ptp_capable_schedule_begin(&state, true, INT64_MAX));
    state = (ptp_capable_schedule_t){.serial = UINT32_MAX};
    assert(ptp_capable_schedule_begin(&state, true, 0) == 1);

    /* A 20 ms polling grid must not turn a 125 ms interval into 140 ms. */
    state = (ptp_capable_schedule_t){0};
    assert(ptp_capable_schedule_request(&state, -3));
    unsigned sent = 0;
    for (int64_t tick = 0; tick < 10000000; tick += 20000) {
        token = ptp_capable_schedule_begin(&state, true, tick);
        if (token) {
            ++sent;
            assert(ptp_capable_schedule_finish(&state, token, true, tick));
        }
    }
    assert(sent == 80);
    assert(ptp_capable_schedule_wait_ms(&state, 9999000, 500) == 1);
    assert(ptp_capable_schedule_wait_ms(&state, 10000000, 500) == 0);
    token = ptp_capable_schedule_begin(&state, true, 10000000);
    assert(token);
    assert(ptp_capable_schedule_wait_ms(&state, 10000001, 500) == 125);
    assert(ptp_capable_schedule_wait_ms(&state, 10125000, 500) == 10);
    assert(ptp_capable_schedule_wait_ms(&state, 11000000, 500) == 0);
    token = ptp_capable_schedule_begin(&state, true, 20000000);
    assert(token && state.next_us == 20125000);
    assert(ptp_capable_schedule_finish(&state, token, true, 20000000));
    assert(!ptp_capable_schedule_begin(&state, true, 20000000));
    assert(ptp_capable_schedule_request(&state, 127));
    assert(ptp_capable_schedule_wait_ms(&state, 20000000, 500) == 500);

    ptp_wifi_peers_t peers = {0};
    uint8_t first_mac[6] = {2, 1}, second_mac[6] = {2, 2};
    ptp_wifi_peer_t *first = ptp_wifi_peers_join(&peers, first_mac);
    ptp_wifi_peer_t *second = ptp_wifi_peers_join(&peers, second_mac);
    ptp_capable_message_t message = {.log_interval = 0};
    message.source_port[7] = 5;
    message.source_port[9] = 1;
    assert(!ptp_wifi_peers_interval(&peers, first_mac, first->association, &message));
    assert(ptp_wifi_peers_capable(&peers, first_mac, first->association, &message, 0));
    message.log_interval = 2;
    assert(!ptp_wifi_peers_interval(&peers, first_mac, first->association + 1, &message));
    message.source_port[9] = 2;
    assert(!ptp_wifi_peers_interval(&peers, first_mac, first->association, &message));
    message.source_port[9] = 1;
    assert(ptp_wifi_peers_interval(&peers, first_mac, first->association, &message));
    assert(first->transmit.interval.log_interval == 2);
    assert(second->transmit.interval.log_interval == 0);
    uint32_t association = first->association;
    token = ptp_capable_schedule_begin(&first->transmit, true, 100);
    assert(!ptp_wifi_peers_sent(&peers, second_mac, association, token, true, 101));
    first = ptp_wifi_peers_join(&peers, first_mac);
    uint32_t replacement = ptp_capable_schedule_begin(&first->transmit, true, 100);
    assert(replacement == token); /* Lifetime disambiguates reused serials. */
    assert(!ptp_wifi_peers_sent(&peers, first_mac, association, token, true, 101));
    assert(ptp_wifi_peers_sent(&peers, first_mac, first->association, replacement, true, 101));
    message.log_interval = 0;
    assert(ptp_wifi_peers_capable(&peers, first_mac, first->association, &message, 200));
    token = ptp_capable_schedule_begin(&first->transmit, true, 1000100);
    assert(token);
    message.source_port[9] = 3;
    assert(ptp_wifi_peers_capable(&peers, first_mac, first->association, &message, 1000200));
    replacement = ptp_capable_schedule_begin(&first->transmit, true, 1000200);
    assert(replacement && replacement != token);
    assert(!ptp_wifi_peers_sent(&peers, first_mac, first->association, token, true, 1000201));
    puts("Association schedule: cadence, nine accepted sends, timeout, duplicate and late completion, request replacement, stop/resume, overflow and peer isolation passed");
}
