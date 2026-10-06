import unittest
from analyze_endpoint import analyze, PERIOD_PS


class EndpointTests(unittest.TestCase):
    def test_rollover_and_invalid_entries(self):
        observations = []
        for local in (281_000_000, 282_000_000):
            mac = local - 100_000
            transmit = mac*1_000_000-5_000_000_000
            receive = transmit-100_000_000
            observations.append(f'FTMLOCAL,{local},{mac},{local+4},1,{receive},{transmit},40000')
            observations.append(f'FTMLOCAL,{local},{mac},{local+4},2,0,0,4294967295')
        result = analyze(observations)
        self.assertEqual(result['valid_entries'], 2)
        self.assertEqual(result['observed_t3_48bit_epoch_crossings'], 1)
        self.assertEqual(result['last_valid_t3_to_report_mac_us']['max'], 5000)
        self.assertEqual(result['mac_minus_local_midpoint_us']['min'], -100002)
        self.assertFalse(result['accuracy_verified'])

    def test_bad_bracket(self):
        self.assertEqual(analyze(['FTMLOCAL,10,20,9,1,2,3,4'])['malformed'], 1)

    def test_counter_step_rejects_unit_rate_model(self):
        result = analyze(['FTMLOCAL,100,80,104,1,1000000,2000000,40000',
                          'FTMLOCAL,200,190,204,2,1000000,2000000,40000'])
        self.assertLess(result['unit_rate_interval_width_us'], 0)
        self.assertFalse(result['accuracy_verified'])
