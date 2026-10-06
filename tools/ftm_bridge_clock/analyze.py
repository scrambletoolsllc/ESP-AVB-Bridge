#!/usr/bin/env python3
"""Summarize live bridge mapping validation, not physical clock accuracy."""
import argparse
import collections
import json
import re
import statistics


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {"count": 0}
    return {"count": len(ordered), "min": ordered[0], "max": ordered[-1],
            "median": statistics.median(ordered),
            "absolute_p95": sorted(map(abs, ordered))[int((len(ordered) - 1) * .95)]}


def analyze(lines):
    statuses = collections.Counter()
    residuals, brackets, ages, rates, upstream, trim_errors = [], [], [], [], [], []
    malformed = 0
    for line in lines:
        match = re.search(r"\b(BRIDGEMAP|UPSTREAM|TIMINGSOURCE|HWRATE),([0-9,\-a-f]+)", line)
        if not match:
            continue
        try:
            fields = match[2].split(",")
            if match[1] == "HWRATE":
                if len(fields) != 6:
                    raise ValueError("hardware rate field count")
                trim_errors.append(int(fields[1]) - (int(fields[2]) / 2**32 - 1) * 1e9)
                continue
            if match[1] in ("UPSTREAM", "TIMINGSOURCE"):
                if len(fields) != 9:
                    raise ValueError("upstream field count")
                if int(fields[1]):
                    upstream.append(int(fields[3]))
                continue
            if len(fields) != 9:
                raise ValueError("mapping field count")
            status, sequence, valid, mac, reference, rate, bracket, age, residual = map(int, fields[0:])
            statuses[status] += 1
            if valid:
                brackets.append(bracket)
                ages.append(age)
                rates.append((rate / 2**32 - 1) * 1e6)
                if residual != -(2**63):
                    residuals.append(residual)
        except ValueError:
            malformed += 1
    return {"statuses": dict(statuses), "malformed": malformed,
            "prediction_residual_ns": distribution(residuals),
            "last_60_prediction_residual_ns": distribution(residuals[-60:]),
            "read_uncertainty_ns": distribution(brackets),
            "snapshot_age_us": distribution(ages),
            "reference_vs_radio_rate_ppm": distribution(rates),
            "sampled_upstream_offset_ns": distribution(upstream),
            "requested_minus_applied_trim_ppb": distribution(trim_errors),
            "physical_accuracy_verified": False,
            "limits": "Read uncertainty excludes fixed skew, upstream path asymmetry and holdover. "
                      "Predictions share the same capture path. Upstream offsets are sampled, not every Sync."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log")
    args = parser.parse_args()
    with open(args.log) as source:
        print(json.dumps(analyze(source), indent=2))
