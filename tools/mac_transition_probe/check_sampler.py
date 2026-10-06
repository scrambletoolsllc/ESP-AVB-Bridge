#!/usr/bin/env python3
"""Check that the linked direct sampler contains its four-read bracket."""
import argparse
import re
import subprocess


def check(disassembly):
    instructions = []
    for line in disassembly.splitlines():
        match = re.match(r'^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(\S+)\s+(.*)$', line)
        if match:
            instructions.append((match[1], match[2], match[3].split('#')[0].strip()))
    windows = []
    for index in range(len(instructions)-3):
        block = instructions[index:index+4]
        if any(instruction[1] != 'lw' for instruction in block):
            continue
        sources = [instruction[2].split(',')[-1].strip() for instruction in block]
        if sources[0] == sources[3] and sources[1] == sources[2] and sources[0] != sources[1]:
            windows.append(block)
    if len(windows) != 1:
        raise ValueError('Expected exactly one consecutive timer/MAC/MAC/timer load window')
    return '\n'.join(' '.join(instruction) for instruction in windows[0])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('elf')
    parser.add_argument('--objdump', required=True)
    args = parser.parse_args()
    disassembly = subprocess.check_output([args.objdump, '-d',
        '--disassemble=mac_transition_sample', args.elf], text=True)
    print(check(disassembly))
