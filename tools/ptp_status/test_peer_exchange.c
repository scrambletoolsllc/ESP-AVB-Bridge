#include <assert.h>
#include <stdio.h>
#include "ptp_peer_exchange.h"

static struct ptp_header_s request;
static struct ptp_delay_resp_s response;
static struct ptp_delay_resp_follow_up_s follow;
static struct timespec transmit = {100, 1000}, receive = {100, 5000};
static ptp_peer_measurement_t measurement;

static void initialize(void)
{
    request.sourceidentity[7] = 1; request.sourceportindex[1] = 1;
    memcpy(response.reqidentity, request.sourceidentity, 8);
    memcpy(response.reqportindex, request.sourceportindex, 2);
    response.header.flags[0] = 2;
    response.header.sequenceid[1] = 42;
    response.header.sourceidentity[7] = 2;
    response.header.sourceportindex[1] = 3;
    follow.header = response.header;
    memcpy(follow.reqidentity, response.reqidentity, 8);
    memcpy(follow.reqportindex, response.reqportindex, 2);
}
static void start(ptp_peer_exchange_t *exchange)
{
    uint32_t generation = ptp_peer_begin(exchange, 42, &request, 1000);
    assert(ptp_peer_publish(exchange, generation, &transmit, 100));
}
int main(void)
{
    initialize();
    ptp_peer_exchange_t exchange = {0};
    assert(!ptp_peer_finish(&exchange, &follow, 200, &measurement));
    uint32_t generation = ptp_peer_begin(&exchange, 42, &request, 1000);
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    assert(exchange.response_rejections==0);
    assert(exchange.response_count==1 && exchange.first_response_us==200);
    ptp_peer_invalidate(&exchange);
    assert(!exchange.response_count && !exchange.response_rejections);
    assert(exchange.lifecycle==1);
    assert(!ptp_peer_publish(&exchange, generation, &transmit, 100));
    start(&exchange);
    assert(exchange.lifecycle==1);
    assert(!ptp_peer_finish(&exchange, &follow, 200, &measurement));
    response.reqportindex[1]++;
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_IGNORED);
    assert(exchange.response_rejections==PTP_PEER_RX_REQUESTER);
    response.reqportindex[1]--;
    response.header.sequenceid[1]++;
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_IGNORED);
    response.header.sequenceid[1]--;
    response.receivetimestamp[6]=255;
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_IGNORED);
    response.receivetimestamp[6]=0;
    response.header.flags[0]=0; /* gPTP ignores this bit on reception. */
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    response.header.flags[0]=2;
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_DUPLICATE);
    assert(exchange.multiple);
    start(&exchange);
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    follow.header.sourceportindex[1]++;
    assert(!ptp_peer_finish(&exchange, &follow, 300, &measurement));
    follow.header.sourceportindex[1]--;
    follow.reqportindex[1]++;
    assert(!ptp_peer_finish(&exchange, &follow, 300, &measurement));
    follow.reqportindex[1]--;
    follow.origintimestamp[6]=255;
    assert(!ptp_peer_finish(&exchange, &follow, 300, &measurement));
    follow.origintimestamp[6]=0;
    assert(ptp_peer_finish(&exchange, &follow, 300, &measurement));
    assert(measurement.transmit.tv_sec==100 && measurement.transmit.tv_nsec==1000);
    assert(measurement.receive.tv_nsec==5000);
    assert(!ptp_peer_finish(&exchange, &follow, 301, &measurement));
    assert(exchange.multiple);
    start(&exchange);
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    response.header.sourceportindex[1]++;
    assert(ptp_peer_response(&exchange, &response, &receive, 400)==PTP_PEER_MULTIPLE);
    response.header.sourceportindex[1]--;
    start(&exchange);
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    response.header.sourceidentity[7]++;
    assert(ptp_peer_response(&exchange, &response, &receive, 201)==PTP_PEER_MULTIPLE);
    assert(!ptp_peer_finish(&exchange, &follow, 300, &measurement));
    response.header.sourceidentity[7]--;
    start(&exchange);
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    assert(!ptp_peer_finish(&exchange, &follow, 1000, &measurement));
    start(&exchange);
    assert(ptp_peer_response(&exchange, &response, &receive, 1000)==PTP_PEER_IGNORED);
    start(&exchange);
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
    generation=exchange.generation;
    start(&exchange); /* A new request invalidates an old response even at the same sequence. */
    assert(!ptp_peer_publish(&exchange, generation, &transmit, 100));
    assert(!ptp_peer_finish(&exchange, &follow, 300, &measurement));
    start(&exchange);
    response.header.sourceidentity[7]=1;
    assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_SELF);
    assert(exchange.multiple);
    response.header.sourceidentity[7]=2;
    for (unsigned index=0;index<70000;index++) {
        uint16_t sequence=(uint16_t)index;
        generation=ptp_peer_begin(&exchange, sequence, &request, 1000);
        assert(ptp_peer_publish(&exchange, generation, &transmit, 100));
        response.header.sequenceid[0]=follow.header.sequenceid[0]=sequence>>8;
        response.header.sequenceid[1]=follow.header.sequenceid[1]=sequence;
        assert(ptp_peer_response(&exchange, &response, &receive, 200)==PTP_PEER_ACCEPTED);
        assert(ptp_peer_finish(&exchange, &follow, 300, &measurement));
    }
    puts("Peer exchange identities, publication invalidation, expiry, duplicates, multiple peers and sequence wrap passed");
}
