import unittest
from analyze_fields import decode,analyze

class FieldsTests(unittest.TestCase):
    def test_known_fields_and_fold(self):
        words=[12345,(23456&0xffffc000)|61,((23456&16383)<<18)|(172<<7)|35]
        self.assertEqual(decode(words)['tx_ticks'],7896168)
        self.assertEqual(decode(words)['rx_ticks'],14998980)
        words[2]=(words[2]&~(2047<<7))|(1876<<7)
        self.assertEqual(decode(words)['correction'],172)
        self.assertEqual(decode(words)['rx_ticks'],14998980)

    def test_exact_match_required(self):
        words=[12345,(23456&0xffffc000)|61,((23456&16383)<<18)|(172<<7)|35]
        base='FTMRESP_BEGIN,1\nFTMRESP,1,100,fc012cfdfe80,6,7896168,14998980,0,0,714,-60,1,0\n'
        meta='FTMRESPMETA,1,0,1,0,'+','.join(map(str,words))+',4\n'
        self.assertEqual(analyze(base+meta)['boots'][0]['counts'],{'verified':1})
        changed=meta.replace(',12345,',',12346,')
        self.assertEqual(analyze(base+changed)['boots'][0]['counts'],{'reconstruction_error':1})
        self.assertEqual(analyze(base+meta.replace(',0,1,0,',',0,2,0,'))['boots'][0]['counts'],{'nonunique_or_absent_slot':1})
        self.assertEqual(analyze(base)['boots'][0]['counts'],{'missing_metadata':1})

if __name__=='__main__':unittest.main()
