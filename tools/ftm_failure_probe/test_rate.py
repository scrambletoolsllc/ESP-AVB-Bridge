import unittest

from analyze_rate import measure, PERIOD
from analyze_rxmeta import reconstruct


def sample(rate_ppm=-53, bias_ps=10000, remote_origin=100_000_000_000):
    entries = []
    for index in range(14):
        elapsed = index * 2_000_000_000
        turnaround = 104_000_000
        remote = lambda value: remote_origin + value + value * rate_ppm // 1_000_000
        entries.append(dict(t1=remote(elapsed) % PERIOD,
                            t2=500_000_000_000_000 + elapsed,
                            t3=500_000_000_000_000 + elapsed + turnaround,
                            t4=(remote(elapsed + turnaround) + bias_ps) % PERIOD,
                            rtt=0xffffffff))
    return dict(entries=entries)


class RateTests(unittest.TestCase):
    def test_known_rate_and_bias_including_negative_rtt(self):
        for rate in (-53, 0, 53):
            for bias in (-5000, 0, 10000):
                result = measure(sample(rate, bias))
                self.assertAlmostEqual(result['receive_rate_ppm'], rate, places=9)
                self.assertAlmostEqual(result['transmit_rate_ppm'], rate, places=9)
                for value in result['rate_adjusted_rtt_ps']:
                    self.assertAlmostEqual(value, bias, places=6)

    def test_remote_wrap_and_full_width_local(self):
        result = measure(sample(remote_origin=PERIOD - 10_000_000_000))
        self.assertAlmostEqual(result['receive_rate_ppm'], -53, places=9)
        self.assertAlmostEqual(result['rate_adjusted_rtt_ps'][-1], 10000, places=6)

    def test_missing_entries_and_bad_order(self):
        report = sample()
        report['entries'][0]['t1'] = 0
        self.assertEqual(len(measure(report)['raw_rtt_ps']), 13)
        report['entries'][3]['t2'] = report['entries'][2]['t2']
        with self.assertRaisesRegex(ValueError, 'nonmonotonic local'):
            measure(report)
        with self.assertRaisesRegex(ValueError, 'fewer than four'):
            measure(dict(entries=[]))

    def test_descriptor_scaling_and_fold(self):
        # One 80 MHz transmit phase step is exactly 12.5 ns.
        raw_t3 = (100000 * 80 + 10 - 640) * 8
        values = (1, 0, 1, raw_t3, 100000, 10, 100, 100000, 10)
        t2, t3, matched = reconstruct(values, 704)
        self.assertTrue(matched)
        changed = (*values[:3], raw_t3 + 8, *values[4:8], 11)
        self.assertEqual(reconstruct(changed, 704)[1] - t3, 12500)
        folded = (*values[:6], 1948, *values[7:])
        self.assertEqual(reconstruct(folded, 704)[0], t2)
        self.assertEqual(t3 - reconstruct(values, 0)[1], 1100000)


if __name__ == '__main__':
    unittest.main()
