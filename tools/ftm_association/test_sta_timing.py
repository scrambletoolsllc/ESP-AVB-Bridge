#!/usr/bin/env python3
"""Exercise the actual STA policy export and FTM control/report admission."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text()
start=source.index('bool ptpd_wifi_sta_timing_snapshot(')
api=source[start:source.index('bool ptpd_wifi_association_snapshot(',start)]
source=(component/'ptp_wifi.c').read_text()
start=source.index('static void on_ftm_control(')
control=source[start:source.index('/* FTM-derived sync markers.',start)]
start=source.index('    if (ptp_ftm_discipline_enabled && ptp_ftm_discipline_enabled()) {',source.index('case WIFI_EVENT_FTM_REPORT:'))
report=source[start:source.index('    if (!ptp_ftm_session_finish',start)]
harness=r'''
#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_association.h"
#include "ptp_wifi_neighbor.h"
#include "ptp_ftm_session.h"
#include "ptp_wifi_capable.h"
#define CONFIG_ESP_PTP_NUM_PORTS 2
static ptp_wifi_media_t s_ftm_media;static uint8_t s_ftm_requested_now;static int s_media_lock __attribute__((unused));
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_wifi_mode_sta 1
static unsigned lock_depth;
#define portENTER_CRITICAL(lock) assert(lock_depth++==0)
#define portEXIT_CRITICAL(lock) assert(--lock_depth==0)
struct ptp_port_s {bool enabled,link_up;int medium,wifi_mode;ptp_wifi_neighbor_t wifi_neighbor;};
struct ptp_state_s {bool gptp;struct ptp_port_s port[2];};
static struct ptp_state_s *s_state;
static bool ptp_is_gptp(const struct ptp_state_s *state){return state->gptp;}
typedef int esp_err_t;
typedef int esp_event_base_t;
typedef struct {uint8_t bssid[6];uint8_t primary;bool ftm_responder;} wifi_ap_record_t;
typedef struct {uint8_t channel,frm_count,burst_period;bool report_vendor_ie;uint8_t resp_mac[6];} wifi_ftm_initiator_cfg_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG 1
#define FTM_CONTROL_START 0
#define FTM_CONTROL_CANCEL 1
#define BIT_STA_CONNECTED 1
#define BIT_FTM_REPORT_OK 2
#define FTM_FRM_COUNT 8
#define FTM_BURST_PERIOD_100MS 0
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
static ptp_ftm_session_t s_ftm_session;
static ptp_wifi_sta_timing_t s_ftm_timing;
static int s_port_index, s_events;
static int64_t s_ftm_associated_us;
static bool s_ftm_waiting_beacon;
static unsigned connected_bits=1,completed_bits,initiations;
static wifi_ap_record_t ap={.bssid={2,1},.primary=6};
static unsigned xEventGroupGetBits(int unused){(void)unused;return connected_bits;}
static void xEventGroupSetBits(int unused,unsigned bits){(void)unused;completed_bits|=bits;}
static esp_err_t esp_wifi_sta_get_ap_info(wifi_ap_record_t *value){*value=ap;return 0;}
static int64_t esp_timer_get_time(void){return 1000;}
static bool precise(void){return true;}
static bool (*ptp_ftm_discipline_enabled)(void)=precise;
static void (*ptp_ftm_report_hook)(void);
static void (*ptp_ftm_begin_hook)(const uint8_t *peer);
static bool ftm_clock_beacon_fresh(void){return true;}
static esp_err_t esp_wifi_ftm_initiate_session(const wifi_ftm_initiator_cfg_t *config){assert(config->channel==6);initiations++;return 0;}
static void cancel_ftm_session(void){ptp_ftm_session_invalidate(&s_ftm_session);}
'''
checks=r'''
int main(void){
 ptp_wifi_sta_timing_t snapshot,original;memset(&snapshot,0xa5,sizeof(snapshot));original=snapshot;
 assert(!ptpd_wifi_sta_timing_snapshot(0,&snapshot));
 struct ptp_state_s state={.gptp=true};s_state=&state;
 struct ptp_port_s *port=&state.port[0];
 port->enabled=port->link_up=true;port->medium=2;port->wifi_mode=1;
 ptp_wifi_neighbor_t *neighbor=&port->wifi_neighbor;
 ptp_wifi_neighbor_associate(neighbor,ap.bssid);
 assert(!ptpd_wifi_sta_timing_snapshot(0,&snapshot));
 on_ftm_control(NULL,0,0,NULL);assert(!initiations && completed_bits==2);
 uint8_t identity[10]={3,0,0,0,0,0,0,0,0,2};
 assert(ptp_wifi_neighbor_bind(neighbor,neighbor->association,ap.bssid,identity));
 assert(ptpd_wifi_sta_timing_snapshot(0,&snapshot) && !snapshot.stopped);
 assert(snapshot.association==neighbor->association && !memcmp(snapshot.bssid,ap.bssid,6));
 assert(!ptpd_wifi_sta_timing_snapshot(-1,&snapshot));assert(!ptpd_wifi_sta_timing_snapshot(2,&snapshot));
 assert(!ptpd_wifi_sta_timing_snapshot(0,NULL));
 on_ftm_control(NULL,0,0,NULL);assert(initiations==1 && s_ftm_session.pending);
 on_ftm_control(NULL,0,0,NULL);assert(initiations==1);
 ptp_interval_message_t request={.log_sync=127};memcpy(request.source_port,identity,10);
 assert(ptp_wifi_neighbor_sync_interval(neighbor,ap.bssid,neighbor->association,&request));
 assert(!finish_report());
 on_ftm_control(NULL,0,0,NULL);assert(initiations==1 && !s_ftm_session.pending);
 request.log_sync=126;assert(ptp_wifi_neighbor_sync_interval(neighbor,ap.bssid,neighbor->association,&request));
 on_ftm_control(NULL,0,0,NULL);assert(initiations==2);
 /* No callback between stop and reset: policy revision still rejects old report. */
 request.log_sync=127;assert(ptp_wifi_neighbor_sync_interval(neighbor,ap.bssid,neighbor->association,&request));
 request.log_sync=126;assert(ptp_wifi_neighbor_sync_interval(neighbor,ap.bssid,neighbor->association,&request));
 assert(!finish_report());
 on_ftm_control(NULL,0,0,NULL);assert(initiations==3 && finish_report());
 on_ftm_control(NULL,0,0,NULL);identity[9]=3;
 assert(ptp_wifi_neighbor_bind(neighbor,neighbor->association,ap.bssid,identity));
 assert(!finish_report());
 on_ftm_control(NULL,0,0,NULL);ptp_wifi_neighbor_associate(neighbor,ap.bssid);
 assert(!finish_report());
 assert(ptp_wifi_neighbor_bind(neighbor,neighbor->association,ap.bssid,identity));
 unsigned before=initiations;
 port->enabled=false;on_ftm_control(NULL,0,0,NULL);port->enabled=true;
 port->link_up=false;on_ftm_control(NULL,0,0,NULL);port->link_up=true;
 port->medium=1;on_ftm_control(NULL,0,0,NULL);port->medium=2;
 port->wifi_mode=2;on_ftm_control(NULL,0,0,NULL);port->wifi_mode=1;
 state.gptp=false;on_ftm_control(NULL,0,0,NULL);state.gptp=true;
 ap.bssid[1]=2;on_ftm_control(NULL,0,0,NULL);ap.bssid[1]=1;
 assert(initiations==before && !lock_depth);
 snapshot=original;port->enabled=false;
 assert(!ptpd_wifi_sta_timing_snapshot(0,&snapshot) && !memcmp(&snapshot,&original,sizeof(snapshot)));
 puts("Actual STA API/control/report: lifecycle, stop, coalesced reset, identity, port guards and lock balance passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory)
 (path/'test.c').write_text(harness+api+control+'\nstatic bool finish_report(void){bool connected=true;'+report+'return ptp_ftm_session_finish(&s_ftm_session,ap.bssid,connected);}\n'+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-address','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
