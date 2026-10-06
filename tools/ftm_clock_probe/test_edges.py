import unittest
from analyze_edges import analyze_edges, parse_edges


def captures():
    hosts, rows = {}, []
    for sequence in range(1, 121):
        cp_us = 2**32 - 5000000 + sequence * 1000005
        host_ticks = sequence * 40000000
        hosts[(1, sequence)] = [1, sequence, host_ticks, host_ticks + 640,
                                sequence * 10**9 + 16500, host_ticks + 680]
        before = cp_us * 40 + 240
        rows.append([1, 2, sequence, int(before / 40 + .2) % 2**32,
                     cp_us * 40, before, before + 40, int(before / 40),
                     int(before / 40) + 10000, sequence * 10**9 + 10000000,
                     sequence * 10**9 + 20000000, sequence])
    return hosts, rows


class EdgeTest(unittest.TestCase):
    def test_frequency_and_mac_wrap(self):
        hosts, rows = captures()
        result = analyze_edges(hosts, rows)
        self.assertAlmostEqual(result['ptp_vs_cp_timer_rate_ppm'], -4.999975, places=4)
        self.assertLess(result['ptp_edge_linear_fit_absolute_residual_us']['max'], .01)
        self.assertGreater(result['mac_offset_interval_width_us_at_fitted_rate'], 0)
        self.assertFalse(result['accuracy_verified'])

    def test_missing_or_stale_edge_rejected(self):
        hosts, rows = captures()
        rows[10][-1] += 1
        result = analyze_edges(hosts, rows + [rows[0]])
        self.assertEqual(result['rejected'], 2)
        self.assertEqual(result['matched'], 119)

    def test_invalid_hardware_latch(self):
        hosts, rows = captures()
        rows[10][4] = rows[10][5] + 100
        self.assertEqual(analyze_edges(hosts, rows)['rejected'], 1)

    def test_parser_separates_records(self):
        hosts, rows = captures()
        lines = ['HOSTEDGE,' + ','.join(map(str, hosts[(1, 1)])),
                 'EDGECLOCK,' + ','.join(map(str, rows[0])),
                 'CLOCK,1,2,3', 'EDGECLOCK,1,2']
        parsed_hosts, groups, rejected = parse_edges(lines)
        self.assertEqual(parsed_hosts[(1, 1)], hosts[(1, 1)])
        self.assertEqual(groups[(1, 2)], rows[:1])
        self.assertEqual(rejected, 1)


if __name__ == '__main__':
    unittest.main()
