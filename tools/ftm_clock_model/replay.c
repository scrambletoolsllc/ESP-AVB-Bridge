#include <inttypes.h>
#include <stdio.h>
#include "ftm_clock_model.h"
int main(void)
{
    ftm_model_t model = {0};
    ftm_model_report_t report;
    unsigned count;
    uint64_t peer;
    char header[512];
    while (fgets(header, sizeof(header), stdin)) {
        uint32_t current_generation;
        int fields=sscanf(header,"%" SCNu32 " %" SCNu32 " %" SCNx64 " %" SCNd64 " %" SCNu32 " %" SCNd64 " %u %" SCNu32 " %" SCNu32,
                 &report.generation, &report.attempt, &peer, &report.before_us,
                 &report.mac_us, &report.after_us, &count, &report.dropped, &current_generation);
        if (fields<8) return 4;
        if (fields==8) current_generation=report.generation;
        if (count > FTM_MODEL_ENTRIES) return 2;
        report.count = count;
        for (unsigned index=0;index<6;++index) report.peer[5-index]=(peer>>(index*8))&255;
        for (unsigned index=0;index<count;++index) {
            ftm_model_entry_t *entry=&report.entries[index];
            if (!fgets(header,sizeof(header),stdin) ||
                sscanf(header,"%" SCNu64 " %" SCNu64 " %" SCNu64 " %" SCNu64 " %" SCNu32,
                      &entry->t1,&entry->t2,&entry->t3,&entry->t4,&entry->rtt)!=5) return 3;
        }
        ftm_model_result_t result={0};
        int status;
        if (current_generation!=report.generation) {
            ftm_model_reset(&model);
            status=FTM_MODEL_STALE;
        } else status=ftm_model_observe(&model,&report,report.after_us,&result);
        ftm_model_snapshot_t snapshot;
        bool valid=ftm_model_snapshot(&model,report.after_us,current_generation,&snapshot);
        printf("%u,%d,%u,%u,%.12f,%.6f,%.6f,%u,%u\n",report.attempt,status,
               result.entries,result.predicted,result.rate_ppm,result.median_error_ps,
               result.max_abs_error_ps,valid,result.wraps);
    }
    return 0;
}
