"""Shared result shape for every component: the choice plus every check behind it."""
from __future__ import annotations

from dataclasses import dataclass, field

OK, WARNING, CANNOT, INVALID = "ok", "warning", "cannot_select", "invalid"
PASS, FAIL, WARN, INFO = "pass", "fail", "warn", "info"


@dataclass
class Check:
    rule: str            # rule id, e.g. R-FLC-05
    requirement: str
    value: str
    verdict: str         # pass | fail | warn | info
    source: str = ""     # document + page, or "hand rule"


@dataclass
class Result:
    component: str
    inputs: dict
    status: str = OK
    value: dict = field(default_factory=dict)
    basis: str = "none"
    checks: list[Check] = field(default_factory=list)

    def add(self, rule, requirement, value, verdict, source=""):
        self.checks.append(Check(rule, requirement, value, verdict, source))
        if verdict == WARN and self.status == OK:
            self.status = WARNING
        return self

    def refuse(self, rule, requirement, value, source=""):
        """Fail closed: no value can be given with the data held."""
        self.checks.append(Check(rule, requirement, value, FAIL, source))
        self.status, self.basis, self.value = CANNOT, "none", {}
        return self

    def invalid(self, message):
        self.checks.append(Check("INPUT", "valid input", message, FAIL))
        self.status, self.basis, self.value = INVALID, "none", {}
        return self

    @property
    def warnings(self) -> list[str]:
        return [c.rule for c in self.checks if c.verdict == WARN]

    def trace(self) -> str:
        head = f"{self.component}: {self.status}"
        if self.value:
            head += " — " + ", ".join(f"{k} = {v:g}" if isinstance(v, float) else f"{k} = {v}"
                                      for k, v in self.value.items())
            head += f" (basis: {self.basis})"
        lines = [head]
        for c in self.checks:
            src = f"  [{c.source}]" if c.source else ""
            lines.append(f"  {c.verdict.upper():5} {c.rule:9} {c.requirement}: {c.value}{src}")
        return "\n".join(lines)
