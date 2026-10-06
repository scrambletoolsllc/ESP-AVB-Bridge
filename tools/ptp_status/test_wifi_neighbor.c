#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_neighbor.h"
int main(void)
{
    ptp_wifi_neighbor_t neighbor={0};
    uint8_t ap[6]={2,1,2,3,4,5}, other[6]={2,1,2,3,4,6};
    uint8_t identity[10]={1,2,3,4,5,6,7,8,0,2};
    assert(!ptp_wifi_neighbor_accepts(&neighbor,ap));
    ptp_wifi_neighbor_associate(&neighbor,ap);
    assert(ptp_wifi_neighbor_accepts(&neighbor,ap));
    assert(!ptp_wifi_neighbor_accepts(&neighbor,other));
    assert(!ptp_wifi_neighbor_accepts(&neighbor,NULL));
    uint32_t first=neighbor.association;
    assert(!ptp_wifi_neighbor_bind(&neighbor,first,other,identity));
    assert(ptp_wifi_neighbor_bind(&neighbor,first,ap,identity));
    assert(neighbor.bound && !memcmp(neighbor.port_identity,identity,10));
    ptp_wifi_neighbor_associate(&neighbor,NULL);
    assert(!neighbor.associated && !neighbor.bound);
    ptp_wifi_neighbor_associate(&neighbor,ap); /* Same BSSID, different association. */
    assert(!neighbor.bound && neighbor.association!=first);
    assert(!ptp_wifi_neighbor_bind(&neighbor,first,ap,identity));
    assert(ptp_wifi_neighbor_bind(&neighbor,neighbor.association,ap,identity));
    ptp_wifi_neighbor_associate(&neighbor,other);
    assert(!neighbor.bound && !ptp_wifi_neighbor_accepts(&neighbor,ap));
    neighbor.association=UINT32_MAX;
    ptp_wifi_neighbor_associate(&neighbor,ap);assert(neighbor.association==1);
    puts("Wi-Fi neighbor association, full MAC match, reconnect invalidation and stale binding rejection passed");
}
