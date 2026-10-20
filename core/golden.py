"""Run a component's golden cases and report every difference."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .provenance import load_yaml
from .result import Result


def compare(case: dict, res: Result, decimals: int = 2) -> list[str]:
    exp, diffs = case["expect"], []
    if res.status != exp["status"]:
        diffs.append(f"status {res.status} ≠ {exp['status']}")
    if "basis" in exp and res.basis != exp["basis"]:
        diffs.append(f"basis {res.basis} ≠ {exp['basis']}")
    for key in [k for k in exp if k not in ("status", "basis", "warnings", "rule")]:
        got = res.value.get(key)
        if exp[key] is None:
            if got is not None:
                diffs.append(f"{key} {got} ≠ none")
        elif isinstance(exp[key], str):
            if got != exp[key]:
                diffs.append(f"{key} {got} ≠ {exp[key]}")
        elif got is None or round(float(got), decimals) != round(float(exp[key]), decimals):
            diffs.append(f"{key} {got} ≠ {exp[key]}")
    if "warnings" in exp and sorted(set(res.warnings)) != sorted(exp["warnings"]):
        diffs.append(f"warnings {sorted(set(res.warnings))} ≠ {exp['warnings']}")
    if "warnings" not in exp and exp["status"] == "ok" and res.warnings:
        diffs.append(f"unexpected warnings {res.warnings}")
    if "rule" in exp and exp["rule"] not in [c.rule for c in res.checks if c.verdict == "fail"]:
        diffs.append(f"refusal rule {exp['rule']} not reported")
    return diffs


def run(cases_file: Path, fn: Callable[..., Result]) -> list[tuple[dict, Result, list[str]]]:
    return [(c, res := fn(**c["in"]), compare(c, res)) for c in load_yaml(cases_file)["cases"]]
