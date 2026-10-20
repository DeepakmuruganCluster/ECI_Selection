"""One input gate for every component's select(): fail closed on bad numbers, never crash.

Applied at the end of each components/<name>/select.py (`select = guarded(select)`), so other components, the web
app and the golden harness all go through it. For every argument annotated as a number:
  - None means "not given": the parameter's own default applies (a required input stays None and the component
    refuses it itself);
  - a numeric string ("7.5") is read as the number; any other string → invalid;
  - NaN or ±infinity → invalid;
  - a negative value → invalid, except temperatures (*_c, down to −60 °C) and altitude (down to −500 m);
  - an int-only parameter (counts, poles, phases) must be a whole number.
An exception raised inside the component is returned as an invalid result, never as a traceback: an engineering
answer is either fully checked or not given (fail closed). Type / value errors are reported as unusable input; failed
lookups (KeyError, IndexError …) as an internal error to report, and logged.
"""
from __future__ import annotations

import functools
import inspect
import math
import sys

from .result import Result

LOWEST = {"_c": -60.0, "altitude_m": -500.0}


def may_be_negative(name: str) -> bool:
    return name.endswith("_c") or name == "altitude_m"


def _lowest(name: str) -> float:
    return LOWEST["_c"] if name.endswith("_c") else LOWEST.get(name, 0.0)


def guarded(fn):
    sig = inspect.signature(fn)
    component = fn.__globals__.get("COMPONENT", fn.__module__.split(".")[-2])

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            bound = sig.bind(*args, **kwargs)
        except TypeError as e:
            return Result(component, dict(kwargs)).invalid(f"inputs not understood: {e}")
        given = dict(bound.arguments)

        def bad(msg):
            return Result(component, {k: v for k, v in given.items() if v is not None}).invalid(msg)

        for name, val in list(bound.arguments.items()):
            p = sig.parameters[name]
            ann = str(p.annotation)
            numeric = ("float" in ann or "int" in ann) and "list" not in ann and "dict" not in ann
            if val is None:
                if p.default is not inspect.Parameter.empty and p.default is not None:
                    bound.arguments[name] = p.default
                continue
            if not numeric:
                continue
            if isinstance(val, bool):
                if "bool" in ann:
                    continue
                return bad(f"{name} must be a number (got {val})")
            if isinstance(val, str):
                try:
                    val = float(val.strip().replace("−", "-"))
                except ValueError:
                    if "str" in ann:
                        continue
                    return bad(f"{name} must be a number (got {val!r})")
            if not isinstance(val, (int, float)):
                return bad(f"{name} must be a number (got {type(val).__name__})")
            if not math.isfinite(val):
                return bad(f"{name} must be a finite number (got {val})")
            if val < _lowest(name):
                return bad(f"{name} cannot be {'below ' + format(_lowest(name), 'g') if may_be_negative(name) else 'negative'} "
                           f"(got {val:g})")
            if "int" in ann and "float" not in ann:
                if val != int(val):
                    return bad(f"{name} must be a whole number (got {val:g})")
                val = int(val)
            bound.arguments[name] = val
        try:
            return fn(*bound.args, **bound.kwargs)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError) as e:
            return bad(f"input not usable ({type(e).__name__}: {e}); nothing selected")
        except (KeyError, IndexError, StopIteration, AttributeError) as e:
            # a lookup that fails is a data or code defect, not the designer's input: say so, still fail closed
            sys.stderr.write(f"{component}: internal error {type(e).__name__}: {e} (inputs {given})\n")
            return bad(f"internal error in {component} ({type(e).__name__}: {e}) — nothing selected; please report it")

    wrapper.__wrapped__ = fn
    return wrapper
