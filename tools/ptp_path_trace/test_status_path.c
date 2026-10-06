#include <assert.h>
#include <stdio.h>
#include "ptp_status_path.h"
int main(void) {
    struct ptpd_status_s status = {0};
    uint8_t output[PTP_PATH_TRACE_MAX_CLOCKS + 1][8];
    memset(status.own_identity_info.id, 0xa0, 8);
    memcpy(status.own_identity_info.btc_id, status.own_identity_info.id, 8);
    memset(status.clock_source_info.btc_id, 1, 8);
    status.clock_source_selected = true;
    status.clock_source_valid = false;
    status.selected_path.count = 5;
    for (unsigned index = 0; index < 5; ++index)
        memset(status.selected_path.identities[index], index + 1, 8);
    assert(ptpd_status_source(&status) == &status.clock_source_info);
    assert(ptpd_status_path(&status, output, 17) == 6);
    assert(!memcmp(output, status.selected_path.identities, 5 * 8));
    assert(!memcmp(output[5], status.own_identity_info.id, 8));
    status.clock_source_valid = true;
    assert(ptpd_status_source(&status) == &status.clock_source_info);
    assert(ptpd_status_path(&status, output, 17) == 6);
    memset(output, 0xee, sizeof(output));
    assert(!ptpd_status_path(&status, output, 5));
    assert(output[0][0] == 0xee);
    status.clock_source_selected = false;
    assert(ptpd_status_source(&status) == &status.own_identity_info);
    assert(ptpd_status_path(&status, output, 17) == 1);
    assert(!memcmp(output[0], status.own_identity_info.id, 8));
    status.clock_source_selected = true;
    status.selected_path.count = 0;
    memset(output, 0xee, sizeof(output));
    assert(ptpd_status_source(&status) == &status.clock_source_info);
    assert(!ptpd_status_path(&status, output, 17));
    assert(output[0][0] == 0xee);
    status.selected_path.count = PTP_PATH_TRACE_MAX_CLOCKS;
    for (unsigned index = 0; index < PTP_PATH_TRACE_MAX_CLOCKS; ++index)
        memset(status.selected_path.identities[index], index + 1, 8);
    assert(ptpd_status_path(&status, output, 17) == 17);
    memcpy(status.selected_path.identities[8], status.own_identity_info.id, 8);
    assert(!ptpd_status_path(&status, output, 17));
    status.selected_path.count++;
    assert(!ptpd_status_path(&status, output, 17));
    puts("Source identity across holdover, complete observed path, capacity and loop tests passed");
}
