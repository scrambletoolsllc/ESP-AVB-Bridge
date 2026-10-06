#include <assert.h>
#include <stdio.h>
#include "ptp_gptp_wire.h"
int main(void) {
    const unsigned types[] = {0,2,3,8,10,11,12};
    for (unsigned index=0;index<sizeof(types)/sizeof(types[0]);++index) {
        uint8_t wire[100], before[100];
        memset(wire,0xa5,sizeof(wire)); wire[0]=0x10|types[index];wire[6]=2;
        memcpy(before,wire,sizeof(wire));
        ptp_gptp_wire_normalize(wire,sizeof(wire),false);
        assert(!memcmp(wire,before,sizeof(wire)));
        ptp_gptp_wire_normalize(wire,sizeof(wire),true);
        assert(wire[1]==0x12 && wire[5]==0 && wire[32]==0);
        for(unsigned offset=0;offset<sizeof(wire);++offset) {
            bool changed=offset==1 || offset==5 || offset==32 || (offset>=16 && offset<20);
            if(types[index]==12 && offset==33)changed=true;
            if(types[index]==11 && ((offset>=34 && offset<44)||offset==46))changed=true;
            if(types[index]==2 && offset>=34 && offset<54)changed=true;
            if(types[index]==0 && offset>=34 && offset<44)changed=true;
            if(!changed)assert(wire[offset]==before[offset]);
            else if(offset==1)assert(wire[offset]==0x12);
            else if(types[index]==12 && offset==33)assert(wire[offset]==0x7f);
            else assert(wire[offset]==0);
        }
        assert(!memcmp(wire+8,before+8,8)); /* Fractional correction preserved. */
        assert(!memcmp(wire+20,before+20,12)); /* Identity and sequence preserved. */
    }
    uint8_t short_wire[33];memset(short_wire,0x77,sizeof(short_wire));
    ptp_gptp_wire_normalize(short_wire,sizeof(short_wire),true);
    for(unsigned index=0;index<sizeof(short_wire);++index)assert(short_wire[index]==0x77);
    uint8_t one_step[44];memset(one_step,0xa5,sizeof(one_step));one_step[0]=0x10;one_step[6]=0;
    ptp_gptp_wire_normalize(one_step,sizeof(one_step),true);
    for(unsigned offset=34;offset<44;++offset)assert(one_step[offset]==0xa5);
    puts("gPTP wire fields normalized; standard profile, one-step origin and timing metadata preserved");
}
