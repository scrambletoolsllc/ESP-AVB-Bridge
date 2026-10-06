#!/usr/bin/env python3
"""Compile the callback selector with the configured C6 toolchain and audit its object."""
from pathlib import Path
import argparse,json,shlex,subprocess
parser=argparse.ArgumentParser()
parser.add_argument('--build',type=Path,default=Path('build-ftm-discipline/coprocessor'))
parser.add_argument('--output',type=Path,default=Path('build-ftm-discipline/association-placement'))
args=parser.parse_args();root=Path(__file__).resolve().parents[2]
commands=json.loads((args.build/'compile_commands.json').read_text())
entry=next(item for item in commands if item['file'].endswith('/ftm_clock_probe.c'))
output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
source=output.with_suffix('.c');object_file=output.with_suffix('.o')
source.write_text('''#include "ftm_association.h"
bool IRAM_ATTR association_probe_select(const ftm_association_state_t *state,
 const uint8_t mac[6], int64_t now_us, int64_t prepared_us, uint8_t output[10]) {
 return ftm_association_select(state, mac, now_us, prepared_us, output);
}
''')
command=shlex.split(entry['command']);compiler=next(arg for arg in command if arg.endswith('-gcc'))
command[command.index('-o')+1]=str(object_file);command[command.index('-c')+1]=str(source)
command.extend(['-I',str(root/'components/ftm_clock_probe')])
subprocess.run(command,cwd=entry['directory'],check=True)
disassembly=subprocess.check_output([compiler[:-3]+'objdump','-drh',str(object_file)],text=True)
symbols=subprocess.check_output([compiler[:-3]+'objdump','-t',str(object_file)],text=True)
undefined=subprocess.check_output([compiler[:-3]+'nm','-u',str(object_file)],text=True)
output.with_suffix('.dis').write_text(disassembly)
if undefined.strip():raise RuntimeError(f'Callback selector has external dependencies: {undefined}')
function=next(line for line in symbols.splitlines() if line.endswith('association_probe_select'))
if '.iram' not in function:raise RuntimeError(f'Selector is not in IRAM: {function}')
report={'selector_symbol':function,'undefined_symbols':[],
        'note':'Object placement only; final firmware placement, DRAM residency and callback runtime still require integration checks.'}
output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
