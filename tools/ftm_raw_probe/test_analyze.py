import unittest
from analyze import parse,analyze
from test_model import report


def encode(reports):
    lines=['FTMRAW_BEGIN,1']
    for data in reports:
        lines.append(f'FTMRAW,{data.generation},{data.attempt},{data.peer},{data.before_us},{data.mac_us},{data.after_us},{len(data.entries)},{data.dropped}')
        for index,entry in enumerate(data.entries):
            lines.append(f'FTMSTAMP,{data.attempt},{index},{entry.token},{entry.rssi},{entry.rtt},{entry.t1},{entry.t2},{entry.t3},{entry.t4},{entry.ppm}')
    return '\n'.join(lines)


class ParserTests(unittest.TestCase):
    def test_complete(self):
        result=analyze(parse(encode([report(index) for index in range(40)])))
        self.assertEqual(result['accepted_reports'],40)
        self.assertEqual(result['predicted_reports'],32)
        self.assertEqual(result['responder_48bit_wraps'],1)

    def test_missing_entry(self):
        text=encode([report(0),report(1)])
        text='\n'.join(line for line in text.splitlines() if not line.startswith('FTMSTAMP,1,4,'))
        with self.assertRaises(ValueError): parse(text)

    def test_truncated_final(self):
        with self.assertRaises(ValueError): parse(encode([report(0)]) .rsplit('\n',1)[0])

    def test_duplicate(self):
        with self.assertRaises(ValueError): parse(encode([report(0),report(0)]))

    def test_mixed_boot(self):
        with self.assertRaises(ValueError): parse(encode([report(0)])+'\n'+encode([report(1)]))

    def test_drop_count_retained(self):
        from dataclasses import replace
        result=analyze(parse(encode([replace(report(0),dropped=3)])))
        self.assertEqual(result['recorder_dropped_reports'],3)

    def test_report_step_counted(self):
        data=[report(index) for index in range(12)]+[report(12,step=100_000_000)]
        result=analyze(parse(encode(data)))
        self.assertEqual(sum(result['rejected_reports'].values()),1)

class GenerationTests(unittest.TestCase):
    def test_backwards_generation_rejected(self):
        with self.assertRaises(ValueError):
            parse(encode([report(0,generation=2),report(1,generation=1)]))

if __name__=='__main__': unittest.main()
