#include <assert.h>
#include <stdio.h>
#include "ptp_peer_capability.h"
int main(void)
{
    ptp_peer_capability_t capability={.lifecycle=7,.received_us=100,.qualified=true};
    assert(ptp_peer_capable(&capability,7,100,100,true,true,true,0,false));
    assert(ptp_peer_capable(&capability,7,399,100,true,true,true,0,false));
    assert(!ptp_peer_capable(&capability,7,400,100,true,true,true,0,false));
    assert(!ptp_peer_capable(&capability,7,99,100,true,true,true,0,false));
    assert(!ptp_peer_capable(&capability,8,101,100,true,true,true,0,false));
    assert(!ptp_peer_capable(&capability,7,101,100,false,true,true,0,false));
    assert(!ptp_peer_capable(&capability,7,101,100,true,false,true,0,false));
    assert(!ptp_peer_capable(&capability,7,101,100,true,true,false,0,false));
    assert(!ptp_peer_capable(&capability,7,101,100,true,true,true,1,false));
    assert(!ptp_peer_capable(&capability,7,101,0,true,true,true,0,false));
    assert(ptp_peer_capable(&capability,7,101,100,true,true,true,1,true));
    assert(!ptp_peer_capable(&capability,7,400,100,true,true,true,1,true));
    capability.qualified=false;
    assert(!ptp_peer_capable(&capability,7,101,100,true,true,true,0,false));
    puts("Wired capability freshness, lifecycle, port/link/profile/domain and qualification gates passed");
}
