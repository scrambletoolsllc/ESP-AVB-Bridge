#!/usr/bin/env python3
"""Exercise the actual station-list wrapper with failed RPC responses."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'managed_components/espressif__esp_hosted/host/drivers/rpc/wrap/rpc_wrap.c').read_text()
start = source.index('int rpc_wifi_ap_get_sta_list(')
end = source.index('\nint rpc_wifi_ap_get_sta_aid(', start)
wrapper = source[start:end]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#define ESP_ERR_INVALID_ARG 258
#define ESP_WIFI_MAX_CONN_NUM 4
#define SUCCESS 0
#define ESP_FAIL -1
typedef struct {
 uint8_t mac[6]; int rssi;
 unsigned phy_11b, phy_11g, phy_11n, phy_lr, phy_11ax, is_mesh_child, reserved;
} station_t;
typedef struct { station_t sta[ESP_WIFI_MAX_CONN_NUM]; int num; } wifi_sta_list_t;
typedef struct { int resp_event_status; union { wifi_sta_list_t wifi_ap_sta_list; } u; } ctrl_cmd_t;
static ctrl_cmd_t request, response;
static ctrl_cmd_t *next_response;
static unsigned calls;
static ctrl_cmd_t *RPC_DEFAULT_REQ(void) { return &request; }
static ctrl_cmd_t *rpc_slaveif_wifi_ap_get_sta_list(ctrl_cmd_t *req) {
 assert(req == &request); ++calls; return next_response;
}
static int rpc_rsp_callback(ctrl_cmd_t *resp) {
 return resp && resp->resp_event_status == SUCCESS ? 0 : ESP_FAIL;
}
'''
checks = r'''
int main(void) {
 wifi_sta_list_t actual;
 memset(&actual, 0xa5, sizeof(actual));
 assert(rpc_wifi_ap_get_sta_list(NULL) == ESP_ERR_INVALID_ARG);
 assert(calls == 0);
 next_response = NULL;
 assert(rpc_wifi_ap_get_sta_list(&actual) == ESP_FAIL);
 assert(actual.num == 0);
 response.resp_event_status = ESP_FAIL;
 response.u.wifi_ap_sta_list.num = 4;
 next_response = &response;
 assert(rpc_wifi_ap_get_sta_list(&actual) == ESP_FAIL);
 assert(actual.num == 0);
 response.resp_event_status = SUCCESS;
 response.u.wifi_ap_sta_list.num = 1;
 memcpy(response.u.wifi_ap_sta_list.sta[0].mac, "abcdef", 6);
 response.u.wifi_ap_sta_list.sta[0].rssi = -42;
 assert(rpc_wifi_ap_get_sta_list(&actual) == 0);
 assert(actual.num == 1);
 assert(memcmp(actual.sta[0].mac, "abcdef", 6) == 0);
 assert(actual.sta[0].rssi == -42);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as work:
    source_path = Path(work) / 'test.c'
    binary = Path(work) / 'test'
    source_path.write_text(harness + wrapper + checks)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g', str(source_path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('Station-list NULL, failed, successful RPC cases passed (ASan/UBSan).')
