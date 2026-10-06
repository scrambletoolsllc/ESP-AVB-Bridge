#!/usr/bin/env python3
"""Reject mixed source/time-base pairs before estimating their rate."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[2]
source = (root / 'components/ftm_endpoint/ftm_endpoint.c').read_text()
start = source.index('static bool report_source_consistent(')
end = source.index('\nbool ptp_ftm_report_hook(', start)
harness = '''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
static bool paired[4];
static struct { uint8_t source_port[10]; uint16_t time_base; uint8_t domain; } fields[4];
'''
checks = '''
int main(void) {
 paired[0] = paired[2] = paired[3] = true;
 fields[1].domain = 99;
 assert(report_source_consistent(0, 3));
 fields[3].source_port[9] = 1;
 assert(!report_source_consistent(0, 3));
 fields[3].source_port[9] = 0;
 fields[2].source_port[0] = 1;
 assert(!report_source_consistent(0, 3));
 fields[2].source_port[0] = 0;
 fields[3].time_base = 1;
 assert(!report_source_consistent(0, 3));
 fields[3].time_base = 0;
 fields[3].domain = 1;
 assert(!report_source_consistent(0, 3));
 fields[3].domain = 0;
 assert(report_source_consistent(0, 3));
}
'''
with tempfile.TemporaryDirectory() as work:
 path = Path(work) / 'test.c'; binary = Path(work) / 'test'
 path.write_text(harness + source[start:end] + checks)
 subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g', str(path), '-o', str(binary)], check=True)
 subprocess.run([str(binary)], check=True)
print('Mixed clock, port, time-base and domain admission cases passed (ASan/UBSan).')
