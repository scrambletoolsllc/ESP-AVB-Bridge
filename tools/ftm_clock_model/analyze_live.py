#!/usr/bin/env python3
"""Compare firmware observer decisions and predictions with native replay."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ftm_raw_probe'))
from analyze import parse, distribution
from model import RelativeModel


def analyze_live(text, replay):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    omitted = False
    try:
        reports = parse(text)
    except ValueError as error:
        if str(error) != 'incomplete final report':
            raise
        headers = list(re.finditer(r'^.*\bFTMRAW,', text, re.M))
        text = text[:headers[-1].start()]
        reports = parse(text)
        omitted = True
    completed = {report.attempt for report in reports}
    skipped = {int(value) for value in re.findall(r'FTMMODEL_SKIPPED,(\d+)', text)}
    firmware = {}
    for line in re.findall(r'\bFTMMODEL,([^\r\n]+)', text):
        fields = line.split(',')
        if len(fields) != 10:
            raise ValueError('malformed model row')
        attempt = int(fields[0])
        if attempt in firmware:
            raise ValueError('duplicate model row')
        if attempt in completed:
            firmware[attempt] = fields
    selected = [report for report in reports if report.attempt not in skipped]
    if set(firmware) != {report.attempt for report in selected}:
        raise ValueError('model rows do not match evaluated complete reports')
    lines = []
    guarded = []
    # A disconnect can invalidate an already queued report before evaluation.
    # Infer this from the event log and subsequent raw association generation,
    # independently of the firmware model status being compared.
    disconnects = [match.start() for match in re.finditer(r'avb_endpoint: Disconnected', text)]
    positions = {int(match[1]): match.start() for match in
                 re.finditer(r'\bFTMMODEL,(\d+),', text)}
    headers = {int(match[1]): match.start() for match in
               re.finditer(r'\bFTMRAW,\d+,(\d+),', text)}
    for report in selected:
        current_generation = report.generation
        for position in disconnects:
            earlier = [other for other in reports if headers[other.attempt] < position]
            later = [other for other in reports if headers[other.attempt] > position
                     and other.generation > report.generation]
            if (position < positions[report.attempt] and earlier and later and
                    earlier[-1].generation == report.generation):
                current_generation = later[0].generation
                guarded.append(report.attempt)
                break
        lines.append(f'{report.generation} {report.attempt} {report.peer} '
                     f'{report.before_us} {report.mac_us} {report.after_us} '
                     f'{len(report.entries)} {report.dropped} {current_generation}')
        lines.extend(f'{entry.t1} {entry.t2} {entry.t3} {entry.t4} {entry.rtt}'
                     for entry in report.entries)
    output = subprocess.check_output([str(replay.resolve())],
                                    input='\n'.join(lines)+'\n', text=True)
    native = [line.split(',') for line in output.splitlines()]
    if len(native) != len(selected):
        raise ValueError('native replay report count differs')
    errors, rates, differences, compute = [], [], [], []
    statuses = Counter()
    rejects, recoveries = [], []
    model = RelativeModel()
    valid_before = False
    previous_generation = None
    for report, row in zip(selected, native):
        live = firmware[report.attempt]
        for index in (0, 1, 2, 3, 7, 8):
            if int(row[index]) != int(live[index]):
                raise ValueError(f'attempt {report.attempt}: field {index} '
                                 f'native={row[index]}, firmware={live[index]}')
        for index, tolerance in ((4, 1e-8), (5, .01), (6, .01)):
            difference = abs(float(row[index])-float(live[index]))
            if difference > tolerance:
                raise ValueError(f'attempt {report.attempt}: numeric field {index} differs')
            if index in (5, 6):
                differences.append(difference)
        compute.append(int(live[9]))
        status = int(row[1])
        statuses[status] += 1
        valid = bool(int(row[7]))
        if report.generation != previous_generation:
            valid_before = False
        if valid and not valid_before:
            recoveries.append(dict(attempt=report.attempt, generation=report.generation,
                                   time_us=report.after_us))
        valid_before, previous_generation = valid, report.generation
        if status:
            rejects.append(dict(attempt=report.attempt, status=status))
            model.reset(None)
            continue
        reference = model.observe(report)
        predicted = reference['predicted_errors_ns']
        if bool(predicted) != bool(int(row[3])):
            raise ValueError('Python prediction validity differs')
        if predicted:
            if (abs(median(predicted)*1000-float(row[5])) > .01 or
                    abs(max(map(abs, predicted))*1000-float(row[6])) > .01):
                raise ValueError('Python prediction differs')
            errors.extend(map(abs, predicted))
            rates.append(reference['remote_rate_ppm'])
    return dict(complete_reports=len(reports), evaluated_reports=len(selected),
                duration_s=(reports[-1].after_us-reports[0].after_us)/1e6,
                intentionally_skipped_reports=len(completed & skipped),
                snapshot_omitted_in_progress_report=omitted,
                recorder_drops=reports[-1].dropped, statuses=dict(statuses),
                association_guarded_reports=guarded,
                rejected_reports=rejects, valid_transitions=recoveries,
                association_generations=sorted({report.generation for report in reports}),
                responder_wraps=sum(int(row[8]) for row in native),
                expiry_events=text.count('FTMMODEL_EXPIRED'),
                test_events=re.findall(r'FTMMODEL_TEST,([^\r\n]+)', text),
                maximum_firmware_vs_native_difference_ps=max(differences, default=0),
                absolute_prediction_error_ns=distribution(errors),
                relative_rate_ppm=distribution(rates), compute_us=distribution(compute),
                ftm_failure_logs=text.count('FTM session failed:'),
                independent_accuracy_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    parser.add_argument('replay', type=Path)
    parser.add_argument('--require-self-test', action='store_true')
    args = parser.parse_args()
    result = analyze_live(args.log.read_text(errors='replace'), args.replay)
    if args.require_self_test:
        expected_events = ['pause_input_begin', 'pause_input_end',
                           'request_rejoin', 'rejoin_result,0']
        if (result['test_events'] != expected_events or
                result['expiry_events'] != 1 or result['recorder_drops'] != 0 or
                result['intentionally_skipped_reports'] == 0 or
                result['statuses'].get(4) != 1+len(result['association_guarded_reports']) or
                set(result['statuses']) != {0, 4} or
                len(result['association_generations']) != 2 or
                len(result['valid_transitions']) != 3 or result['responder_wraps'] < 1):
            raise ValueError(f'incomplete or failed self-test: {result}')
        stale_attempt = result['rejected_reports'][0]['attempt']
        if result['valid_transitions'][1]['attempt'] != stale_attempt+8:
            raise ValueError('expiry recovery did not require eight new reports')
    print(json.dumps(result, indent=2))
