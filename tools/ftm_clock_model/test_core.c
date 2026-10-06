#include <assert.h>
#include <math.h>
#include <string.h>
#include "ftm_clock_model.h"
static ftm_model_report_t sample(unsigned index)
{
    const uint64_t period = UINT64_C(1)<<48;
    uint64_t local=UINT64_C(400000000000000)+index*UINT64_C(500000000000);
    uint64_t elapsed=index*UINT64_C(500000000000);
    uint64_t remote=period-UINT64_C(2000000000000)+elapsed+elapsed/50000;
    ftm_model_report_t report={.generation=1,.attempt=index+1,.count=1};
    report.before_us=(local+UINT64_C(5100000000))/1000000;
    report.after_us=report.before_us+1;
    report.mac_us=report.before_us;
    report.entries[0]=(ftm_model_entry_t){.t1=remote%period,.t2=local,
        .t3=local+100000000,.t4=(remote+100002000)%period,.rtt=2000};
    return report;
}
int main(void)
{
    ftm_model_t model={0}; ftm_model_result_t result;
    ftm_model_snapshot_t snapshot;
    ftm_model_report_t report;
    unsigned wraps=0;
    for(unsigned index=0;index<40;++index) {
        report=sample(index);
        assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
        wraps+=result.wraps;
    }
    assert(wraps==1);
    assert(ftm_model_snapshot(&model,report.after_us,1,&snapshot));
    assert(!ftm_model_snapshot(&model,report.after_us+2000001,1,&snapshot));
    assert(!ftm_model_snapshot(&model,report.after_us,2,&snapshot));
    report=sample(40);report.generation=2;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    assert(!result.predicted && model.count==1);
    report=sample(41);report.generation=2;report.dropped=1;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_DROPPED);
    assert(!model.snapshot.valid);
    report=sample(0);report.entries[0].t2=UINT64_MAX;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_INPUT);
    report=sample(0);
    assert(ftm_model_observe(&model,&report,report.after_us+500001,&result)==FTM_MODEL_INPUT);
    report=sample(0);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_STALE);

    /* A gap expires the old fit, then new reports must warm up again. */
    report=sample(10);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    report=sample(15);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_STALE);
    assert(!model.snapshot.valid && model.count==0);
    for (unsigned index=16;index<24;++index) {
        report=sample(index);
        assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
        assert(!result.predicted);
        assert(model.snapshot.valid==(index==23));
    }
    assert(fabs(model.snapshot.rate_delta*1e6-20)<1e-8);
    report=sample(24);
    report.entries[0].t1+=30000000;
    report.entries[0].t4+=30000000;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_INNOVATION);
    assert(!model.snapshot.valid);

    report=sample(0);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    report=sample(1);
    report.entries[0].t1+=3000000000;
    report.entries[0].t4+=3000000000;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_REMOTE_STEP);
    report=sample(0);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    report=sample(1);
    report.entries[0].t2-=1000000000000;
    report.entries[0].t3-=1000000000000;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_LOCAL_STEP);

    /* Coarse MAC wrap does not truncate full-width initiator stamps. */
    const uint64_t mac_period=(UINT64_C(1)<<32)*1000000;
    const uint64_t shift=mac_period-UINT64_C(401000000000000);
    uint32_t previous_mac=0;
    unsigned mac_wraps=0;
    for (unsigned index=0;index<40;++index) {
        report=sample(index);
        report.entries[0].t2+=shift;
        report.entries[0].t3+=shift;
        report.before_us+=shift/1000000;
        report.after_us+=shift/1000000;
        report.mac_us=report.before_us;
        if (index && report.mac_us<previous_mac) ++mac_wraps;
        previous_mac=report.mac_us;
        assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    }
    assert(mac_wraps==1 && model.snapshot.valid);
    report=sample(0);
    report.peer[0]=1;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_OK);
    assert(model.count==1 && !result.predicted && !model.snapshot.valid);
    ftm_model_reset(&model);
    for (unsigned index=0;index<8;++index) {
        report=sample(index);
        uint64_t extra=index*UINT64_C(500000000);
        const uint64_t period=UINT64_C(1)<<48;
        report.entries[0].t1=(report.entries[0].t1+extra)%period;
        report.entries[0].t4=(report.entries[0].t4+extra)%period;
        assert(ftm_model_observe(&model,&report,report.after_us,&result)==
               (index==7 ? FTM_MODEL_RATE : FTM_MODEL_OK));
    }
    assert(!model.snapshot.valid);
    report=sample(0);report.entries[0].rtt=UINT32_MAX;
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_INPUT);
    report=sample(0);report.entries[0].rtt=UINT32_C(4294965733);
    assert(ftm_model_observe(&model,&report,report.after_us,&result)==FTM_MODEL_INPUT);
    return 0;
}
