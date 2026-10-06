import unittest
from analyze_paired import analyze, ticks_to_ps, PERIOD
from analyze import analyze as analyze_failure


def logs(token=6, received_token=6, offset=0):
    raw_t1 = 2 * PERIOD
    raw_t4 = raw_t1 + 80000
    t1 = ticks_to_ps(raw_t1 + 706) + offset
    t4 = ticks_to_ps(raw_t4)
    responder = ('FTMRESP_BEGIN,1\n'
                 f'FTMRESP,1,100,fc012cfdfe80,{token},{raw_t1},{raw_t4},'
                 f'{t1},{t4},706,-60,1,0\n')
    endpoint = ('FTMDEBUG_BEGIN,1\n'
                'FTMDEBUG,1,100,5,0,16,1,3,1,0,704,0,0,0\n'
                f'FTMREJECT,1,0,{received_token},-60,4294965733,'
                f'{t1 % PERIOD},1000000000,{1000000000 + t4-t1 + 1563},{t4 % PERIOD},0\n')
    return endpoint, responder


class PairedTests(unittest.TestCase):
    def test_aborted_entries_are_not_treated_as_classified_rtts(self):
        endpoint, _ = logs()
        endpoint = endpoint.replace('FTMDEBUG,1,100,5,', 'FTMDEBUG,1,100,6,')
        endpoint = endpoint.replace(',4294965733,', ',0,')
        result = analyze_failure(endpoint)['statuses'][6]
        self.assertFalse(result['rtt_fields_classified'])
        self.assertEqual(result['rtt_field_disagreements'], 0)

    def test_exact_match_across_remote_epoch(self):
        result = analyze(*logs())
        self.assertEqual(result['responder_conversion_errors'], {})
        self.assertEqual(result['statuses'][5]['matched_entries'], 1)
        self.assertEqual(result['statuses'][5]['rtt_ps']['median'], -1563)

    def test_conversion_and_token_disagreements_are_visible(self):
        result = analyze(*logs(received_token=7, offset=1000))
        self.assertEqual(result['responder_conversion_errors'], {'t1': 1})
        self.assertEqual(result['statuses'][5]['token_mismatches'], 1)

    def test_unmatched_and_duplicate_timestamps_are_not_guessed(self):
        endpoint, responder = logs()
        missing = analyze(endpoint.replace('FTMREJECT,1,0,6,-60,4294965733,',
                                          'FTMREJECT,1,0,6,-60,4294965733,1'), responder)
        self.assertEqual(missing['statuses'][5]['unmatched_entries'], 1)
        responder += responder.splitlines()[1].replace('FTMRESP,1,', 'FTMRESP,2,') + '\n'
        self.assertEqual(analyze(endpoint, responder)['statuses'][5]['ambiguous_matches'], 1)

    def test_reboots_require_explicit_opt_in_and_keep_ambiguity(self):
        endpoint, responder = logs()
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            analyze(endpoint, responder + responder)
        result = analyze(endpoint, 'FTMRESP_BEGIN,1\n' + responder,
                         allow_responder_reboots=True)
        self.assertEqual(result['responder_boots'], 2)
        self.assertEqual(result['statuses'][5]['matched_by_responder_boot'], {2: 1})
        result = analyze(endpoint, responder + responder, allow_responder_reboots=True)
        self.assertEqual(result['statuses'][5]['ambiguous_matches'], 1)


if __name__ == '__main__':
    unittest.main()
