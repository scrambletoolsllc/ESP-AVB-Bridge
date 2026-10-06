import unittest
from analyze import summarize


def record(round_number=0, lower=100, upper=104, held_lower=101, held_upper=103,
           train=10, held=10, violations=0, miss=0):
    return 'MAC_TRANSITION,' + ','.join(map(str, [round_number, 30000000+round_number*2280000, 1280000,
        train, held, 0, 2048-train-held, lower, upper, held_lower, held_upper,
        violations, miss, 25, 30])) + '\n'


class AnalysisTests(unittest.TestCase):
    def test_consistent_intervals(self):
        result = summarize(record() + 'MAC_TRANSITION_END')
        self.assertEqual(result['global_interval_width_ns'], 50)
        self.assertEqual(result['training_interval_width_ns']['median'], 100)
        self.assertTrue(result['completed'])

    def test_step_between_rounds(self):
        result = summarize(record() + record(1, 200, 204, 201, 203))
        self.assertLess(result['global_interval_width_ns'], 0)
        self.assertEqual(result['training_midpoint_span_ns'], 2500)

    def test_invalid_training_interval(self):
        self.assertEqual(summarize(record(lower=105))['usable_rounds'], 0)
        self.assertEqual(summarize(record(train=0))['usable_rounds'], 0)

    def test_heldout_violation(self):
        result = summarize(record(held_lower=110, held_upper=114, violations=3, miss=8))
        self.assertEqual(result['heldout_midpoint_violations'], 3)
        self.assertEqual(result['heldout_max_miss_ns'], 200)

    def test_malformed(self):
        with self.assertRaises(ValueError):
            summarize('MAC_TRANSITION,1,2')

    def test_inconsistent_heldout_not_hidden(self):
        result = summarize(record(held_lower=120, held_upper=90, violations=4, miss=3))
        self.assertEqual(result['heldout_midpoint_violations'], 4)
        self.assertFalse(result['consistent'])

    def test_duplicate_or_missing_round(self):
        for text in (record()+record(), record()+record(2)):
            with self.assertRaises(ValueError):
                summarize(text)

    def test_bad_count(self):
        with self.assertRaises(ValueError):
            summarize(record(violations=11))

    def test_bad_numeric_suffix(self):
        with self.assertRaises(ValueError):
            summarize(record().strip()+'garbage')

    def test_abort_cannot_pass_completion(self):
        result = summarize(record()+'MAC_TRANSITION_ABORT,counter_discontinuity\nMAC_TRANSITION_END')
        self.assertFalse(result['completed'])
        self.assertFalse(result['validated_run'])

    def test_excess_training_count(self):
        with self.assertRaises(ValueError):
            summarize(record(train=1025))


if __name__ == '__main__':
    unittest.main()
