# Responder fine timestamp diagnostics

`CONFIG_FTM_RESPONDER_RX_METADATA` is default off and depends on the existing
responder probe. The wrapper invokes the original driver callback first,
then reads the audited timestamp-slot register bank. It scans 16 slots,
accepting only stable exact T1 and T4 reconstruction. Formatting and UART
output remain in the worker task. The probe does not change compensation.

Private register layout is derived from the hash-gated lmac_record_txtime
object, not a public hardware interface. The original routine reads the
shared timestamp words repeatedly. Post-callback matching checks whether
these fields still belong to the observed exchange; zero or multiple matches
and unstable reads remain explicit diagnostic failures. This adds callback
work and UART traffic, and is not a timing-neutral accuracy test.

`FTMRESPMETA` fields: responder sequence, slot, exact stable match count,
unstable-candidate count, three raw words, scan duration in microseconds.
The sequence joins the preceding FTMRESP record within the same boot.
Do not interpret fields when match count differs from one. Duration covers
scan/reconstruction work, not the entire wrapper, queueing or worker logging.

`analyze_fields.py` decodes and validates the words independently in Python.
It reports missing metadata, missing original timestamps, failed slot
matches, instability and reconstruction disagreements separately. Use a
frozen complete UART window, allowing the two loggers to drain independently.
Existing paired analysis still verifies that the endpoint received precisely
the same responder timestamps and dialog token.

Native checks:

```
cc -Wall -Wextra -Werror -fsanitize=undefined \
  -I components/ftm_responder_probe tools/ftm_responder_probe/test_fields.c \
  -o /tmp/test_ftm_responder_fields
/tmp/test_ftm_responder_fields
python3 -B -m unittest discover -s tools/ftm_responder_probe -p 'test_*.py'
python3 tools/ftm_responder_probe/analyze_fields.py CAPTURE.log
```

For words A/B/C, TX ticks are `(A*80 + (B&127) - 640)*8`.
RX coarse is `(B&0xffffc000) | (C>>18)`, RX phase is `C&127`, and
encoded correction is `(C>>7)&2047`. Corrections with bit 10 set fold to
`2048-encoded`. RX ticks are `coarse*640 - 13312 + phase*8 + correction`.
These are tick values, prior to responder compensation and conversion to ps.
The initial failed experiment read correction from the next register; its
nine-field metadata records must not be mixed with the corrected eight-field
format. Exact hardware reconstruction, not synthetic tests alone, is the
acceptance criterion.
