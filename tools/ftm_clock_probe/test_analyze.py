import unittest
from analyze import analyze, parse, FIELDS


def exchanges(forward=30, reverse=30, ppm=12):
    rows = []
    rate = 1 + ppm / 1e6
    for sequence in range(200):
        host = sequence * 200000 + 1000000
        receive = round(rate * (host + forward) + 9000)
        mac = receive + 2 + (2**32 - 2000000)
        rows.append(dict(zip(FIELDS, [1, 2, sequence, host - 1, (host - 1) * 1000,
            host, receive, receive + 1, mac % 2**32, receive + 3,
            receive + 3, receive + 3000, receive + 5, receive + 10,
            host + forward + reverse + 10, (host + forward + reverse + 10) * 1000,
            host + forward + reverse + 11])))
    return rows


class ProbeTest(unittest.TestCase):
    def test_drift_and_mac_wrap(self):
        result = analyze(exchanges())
        self.assertAlmostEqual(result['estimated_cp_relative_rate_ppm'], 12, delta=.01)
        self.assertLess(result['mac_minus_local_spread_us'], 2)
        self.assertAlmostEqual(result['transport_rtt_us_approx']['p50'], 60)

    def test_asymmetric_path_does_not_claim_accuracy(self):
        result = analyze(exchanges(forward=1000, reverse=10))
        self.assertFalse(result['accuracy_verified'])
        self.assertGreater(result['offset_interval_width_us_at_fitted_rate'], 1000)
        self.assertLess(result['midpoint_offset_spread_us'], 2)

    def test_duplicates_corruption_reboot_and_reordering(self):
        rows = exchanges()[:3]
        reboot = dict(rows[0], host_boot=7)
        broken = dict(rows[0], sequence=8, host_receive=0)
        lines = ['prefix CLOCK,' + ','.join(str(row[key]) for key in FIELDS)
                 for row in [rows[2], rows[0], rows[1], rows[0], reboot, broken]]
        groups, rejected = parse(lines + ['CLOCK,garbage', 'FTMCLOCK,1,2,3'])
        self.assertEqual(rejected, 3)
        self.assertEqual(len(groups), 2)
        self.assertEqual(analyze(groups[(1, 2)])['samples'], 3)

    def test_ptp_step_reported(self):
        rows = exchanges()
        rows[-1]['host_ptp'] += 1000000
        self.assertEqual(len(analyze(rows)['ptp_discontinuities_over_100us']), 1)

    def test_slow_ptp_read_is_not_a_clock_step(self):
        rows = exchanges()
        rows[80]['host_ptp'] += 180000
        rows[80]['host_after'] += 200
        rows[80]['host_receive'] += 200
        rows[80]['receive_after'] += 200
        rows[80]['receive_ptp'] += 200000
        for field in ('cp_receive', 'mac_before', 'mac', 'mac_after',
                      'tsf_before', 'tsf', 'tsf_after', 'cp_send'):
            rows[80][field] += 200
        self.assertEqual(analyze(rows)['ptp_discontinuities_over_100us'], [])


if __name__ == '__main__':
    unittest.main()
