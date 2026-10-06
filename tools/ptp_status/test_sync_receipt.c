#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include "ptp_sync_receipt.h"
int main(void) {
 ptp_sync_receipt_t timer={0};
 assert(!ptp_sync_receipt_current(&timer,0));
 for(int interval=-128;interval<=127;++interval) {
  int64_t duration=ptp_sync_receipt_interval(interval);
  if(interval < -24 || interval > 24) { assert(!duration);continue; }
  assert(duration>0);
  ptp_sync_receipt_start(&timer,1000000,375000);
  assert(ptp_sync_receipt_observe(&timer,1000000,interval,1000000));
  assert(ptp_sync_receipt_current(&timer,1000000+duration-1));
  assert(!ptp_sync_receipt_current(&timer,1000000+duration));
  assert(!ptp_sync_receipt_current(&timer,999999));
  ptp_sync_receipt_t before=timer;
  assert(!ptp_sync_receipt_observe(&timer,1000000,interval,1000000+duration));
  assert(!ptp_sync_receipt_observe(&timer,999999,interval,1000000));
  assert(!ptp_sync_receipt_observe(&timer,1000001,interval,1000000));
  assert(!memcmp(&timer,&before,sizeof(timer)));
 }
 ptp_sync_receipt_start(&timer,INT64_MAX-10,375000);
 assert(ptp_sync_receipt_current(&timer,INT64_MAX));
 ptp_sync_receipt_start(&timer,-1,375000);assert(!timer.armed);
 ptp_sync_receipt_start(&timer,100,0);assert(!timer.armed);
 ptp_sync_receipt_start(&timer,1000000,375000);
 assert(ptp_sync_receipt_wait_ms(&timer,1000000,500)==375);
 assert(ptp_sync_receipt_wait_ms(&timer,1000000,50)==50);
 assert(ptp_sync_receipt_wait_ms(&timer,1374999,50)==1);
 assert(ptp_sync_receipt_wait_ms(&timer,1375000,50)==0);
 assert(ptp_sync_receipt_wait_ms(&timer,999999,50)==0);
 ptp_sync_receipt_start(&timer,0,INT64_MAX);
 assert(ptp_sync_receipt_wait_ms(&timer,0,500)==500);
 puts("Sync receipt timer: supported intervals, exact boundaries, queue age, ordering, future timestamps, overflow-safe elapsed time");
}
