#include <assert.h>
#include <stdio.h>
#include "ptp_source_loss_probe.h"
int main(void) {
 ptp_source_loss_probe_t probe={0};
 assert(!ptp_source_loss_probe_tick(&probe,100,false));
 assert(!ptp_source_loss_probe_drop(&probe,11));
 assert(ptp_source_loss_probe_tick(&probe,100,true));
 const int64_t restore=30000000+CONFIG_ESP_PTP_SOURCE_LOSS_ANNOUNCE_SECONDS*INT64_C(1000000);
 const int64_t boundaries[]={0,29999999,30000000,restore-1,restore,restore+11999999,restore+12000000,restore+15999999,restore+16000000,restore+90000000};
 const unsigned phases[]={0,0,1,1,2,2,3,3,4,4};
 for(unsigned index=0;index<10;++index) {
  ptp_source_loss_probe_tick(&probe,100+boundaries[index],false);
  assert(probe.phase==phases[index]);
  for(unsigned type=0;type<16;++type)
   assert(ptp_source_loss_probe_drop(&probe,type)==((probe.phase==1 && type==11)||(probe.phase==3 && (type==0||type==8))));
 }
 assert(probe.dropped[1]==2 && probe.dropped[3]==4);
 assert(!ptp_source_loss_probe_tick(&probe,99,true));
 assert(probe.phase==4);
 puts("Finite source loss: precise boundaries, Pdelay/Signaling preserved, autonomous restoration");
}
