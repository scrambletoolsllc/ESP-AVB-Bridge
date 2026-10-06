import unittest
from model import (extend_near, fine_mac_ticks, RelativeModel, Report, Entry,
                   REMOTE_PERIOD, MAC_PERIOD, PS_PER_US)


def report(index, origin=REMOTE_PERIOD-2_000_000*PS_PER_US, generation=1,
           local_origin=400_000_000*PS_PER_US, rate_ppm=20, step=0):
    local = local_origin+index*500_000*PS_PER_US
    entries=[]
    for offset in range(14):
        arrival=local+offset*1000*PS_PER_US
        departure=arrival+100*PS_PER_US
        remote=lambda value: origin+(value-local_origin)+((value-local_origin)*rate_ppm)//1_000_000+step
        entries.append(Entry(offset+1,-60,10000,(remote(arrival)-5000)%REMOTE_PERIOD,
                             arrival,departure,(remote(departure)+5000)%REMOTE_PERIOD))
    callback=entries[-1].t3+5000*PS_PER_US
    return Report(generation,index+1,'d885acfa2c59',callback//PS_PER_US,
                  (callback//PS_PER_US)%(1<<32),callback//PS_PER_US+1,0,tuple(entries))


class ModelTests(unittest.TestCase):
    def test_unsigned_negative_rtt_rejected(self):
        from dataclasses import replace
        original = report(0)
        entries = tuple(replace(entry, rtt=4294965733) for entry in original.entries)
        with self.assertRaises(ValueError):
            RelativeModel().observe(replace(original, entries=entries))

    def test_nearest_wrap(self):
        self.assertEqual(extend_near(3,98,100,10),103)
        self.assertEqual(extend_near(98,3,100,10),-2)

    def test_ambiguity_and_stale(self):
        for arguments in [(50,0,100,49),(20,0,100,10),(101,0,100,10)]:
            with self.assertRaises(ValueError): extend_near(*arguments)

    def test_fine_counter_wrap(self):
        coarse=1500
        lower,upper=fine_mac_ticks(coarse,59990,10,20)
        self.assertEqual((lower,upper),(60000,60010))

    def test_fine_mac_large_epoch(self):
        coarse=(1<<32)-1
        lower,upper=fine_mac_ticks(coarse,(coarse*40-230)%60000,230,240)
        self.assertEqual((lower,upper),(coarse*40,coarse*40+10))

    def test_prediction_and_responder_wrap(self):
        model=RelativeModel()
        results=[model.observe(report(index)) for index in range(80)]
        self.assertEqual(sum(result['responder_wraps'] for result in results),1)
        self.assertAlmostEqual(results[-1]['remote_rate_ppm'],20,places=6)
        self.assertLess(max(abs(error) for result in results for error in result['predicted_errors_ns']),1)

    def test_local_mac_32bit_wrap(self):
        model=RelativeModel()
        results=[model.observe(report(index,local_origin=MAC_PERIOD-2_000_000*PS_PER_US)) for index in range(20)]
        self.assertEqual(results[-1]['segment'],1)
        self.assertAlmostEqual(results[-1]['remote_rate_ppm'],20,places=6)

    def test_generation_resets(self):
        model=RelativeModel()
        for index in range(12): model.observe(report(index))
        result=model.observe(report(0,generation=2))
        self.assertEqual(result['segment'],2)
        self.assertIsNone(result['remote_rate_ppm'])

    def test_stale_and_backwards(self):
        for index in (0,10):
            model=RelativeModel()
            model.observe(report(0))
            with self.assertRaises(ValueError): model.observe(report(index))

    def test_step_rejected_without_mutation(self):
        model=RelativeModel()
        for index in range(12): model.observe(report(index))
        previous=model.previous
        with self.assertRaises(ValueError): model.observe(report(12,step=100_000_000))
        self.assertEqual(model.previous,previous)

    def test_stale_callback(self):
        from dataclasses import replace
        model=RelativeModel()
        data=report(0)
        with self.assertRaises(ValueError):
            model.observe(replace(data,mac_us=(data.mac_us+600000)%(1<<32)))

    def test_rate_limit(self):
        model=RelativeModel()
        with self.assertRaises(ValueError):
            for index in range(12): model.observe(report(index,rate_ppm=500))


class BoundaryTests(unittest.TestCase):
    def test_fine_phase_all_positions_across_wrap(self):
        for coarse in [0,1,1499,1500,1501,(1<<32)-2,(1<<32)-1]:
            for fraction in range(40):
                ticks=coarse*40+fraction
                phase=(ticks-235)%60000
                lower,upper=fine_mac_ticks(coarse,phase,230,240)
                self.assertLessEqual(lower,ticks)
                self.assertGreaterEqual(upper,ticks)
                self.assertEqual(upper-lower,10)

    def test_full_local_timestamp_not_truncated(self):
        model=RelativeModel()
        first=report(0,local_origin=5*REMOTE_PERIOD)
        self.assertGreater(first.entries[0].t2,REMOTE_PERIOD)
        result=model.observe(first)
        self.assertEqual(result['entries'],14)

    def test_bad_calibration_and_phase(self):
        for arguments in [(0,60000,0,10),(0,0,10,0),(0,0,0,41)]:
            with self.assertRaises(ValueError): fine_mac_ticks(*arguments)

    def test_report_expired_before_fit(self):
        model=RelativeModel()
        for index in range(12): model.observe(report(index))
        with self.assertRaises(ValueError): model.observe(report(30))

    def test_peer_change_discards_old_fit(self):
        from dataclasses import replace
        model=RelativeModel()
        for index in range(12): model.observe(report(index))
        changed=replace(report(12),peer='010203040506')
        result=model.observe(changed)
        self.assertIsNone(result['remote_rate_ppm'])
        self.assertEqual(result['segment'],2)

if __name__=='__main__': unittest.main()
