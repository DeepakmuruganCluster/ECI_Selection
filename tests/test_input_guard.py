"""Fail closed on bad input, in every component (test agent findings, 2026-10-14).

For each component and each numeric input, start from the component's first selected golden case and replace that
one input with NaN, ±infinity, a negative number (where the quantity cannot be negative), a non-numeric string or
None. The result must never be an uncaught exception, and a bad number must never come back as ok / warning.
None means "not given": the component's own default or its own refusal applies.
"""
import importlib
import inspect
import math
import pkgutil
from pathlib import Path

import pytest
import yaml

import components
from core.guard import may_be_negative

ROOT = Path(__file__).resolve().parents[1]
BAD = [("nan", float("nan")), ("inf", float("inf")), ("-inf", float("-inf")), ("text", "abc")]


def _cases():
    out = []
    for name in sorted(m.name for m in pkgutil.iter_modules(components.__path__)):
        mod = importlib.import_module(f"components.{name}.select")
        golden = yaml.safe_load((ROOT / "components" / name / "golden" / "cases.yaml").read_text())["cases"]
        base = next((c["in"] for c in golden if c["expect"]["status"] in ("ok", "warning")), None)
        if base is None:
            continue
        for p in inspect.signature(mod.select).parameters.values():
            ann = str(p.annotation)
            if not ("float" in ann or "int" in ann) or "bool" in ann:
                continue
            for label, val in BAD + ([("negative", -1)] if not may_be_negative(p.name) else []):
                out.append(pytest.param(mod.select, base, p.name, val, id=f"{name}-{p.name}-{label}"))
            out.append(pytest.param(mod.select, base, p.name, None, id=f"{name}-{p.name}-none"))
    return out


@pytest.mark.parametrize("select,base,name,bad", _cases())
def test_bad_input_fails_closed(select, base, name, bad):
    res = select(**{**base, name: bad})          # must not raise
    if bad is None:
        return
    assert res.status in ("invalid", "cannot_select"), f"{name}={bad!r} → {res.status}\n{res.trace()}"


def test_numeric_strings_are_read_as_numbers():
    from components.motor_flc.select import select
    assert select(kw="7.5").value == select(kw=7.5).value


def test_unexpected_errors_become_invalid():
    from components.control_circuit.select import select
    r = select(supply="transformer", coil_power=[{"close_va": "x"}])
    assert r.status == "invalid"
    assert "Traceback" not in r.trace()
