from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecurityHit:
    rule_id: str
    title: str
    severity: str
    evidence: dict[str, Any]


_RULES: list[tuple[SecurityHit, re.Pattern[str]]] = [
    (
        SecurityHit(
            rule_id="SEC001",
            title="Hardcoded password/secret",
            severity="high",
            evidence={},
        ),
        re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"][^'\"]+['\"]"),
    ),
    (
        SecurityHit(
            rule_id="SEC002",
            title="Possible SQL injection (string concatenation)",
            severity="high",
            evidence={},
        ),
        re.compile(r"(?i)\b(select|insert|update|delete)\b.+['\"]\s*\+\s*\w+"),
    ),
    (
        SecurityHit(
            rule_id="SEC003",
            title="Use of eval/exec",
            severity="critical",
            evidence={},
        ),
        re.compile(r"(?i)\b(eval|exec)\s*\("),
    ),
    (
        SecurityHit(
            rule_id="SEC004",
            title="Insecure deserialization (pickle)",
            severity="high",
            evidence={},
        ),
        re.compile(r"(?i)\bpickle\.loads?\s*\("),
    ),
    (
        SecurityHit(
            rule_id="SEC005",
            title="Potential command injection (shell=True)",
            severity="high",
            evidence={},
        ),
        re.compile(r"(?i)\bshell\s*=\s*True\b"),
    ),
]


def scan_security_risks(code: str) -> list[dict[str, Any]]:
    """Detects risky patterns in source code using local regex rules.

    Returns:
        List of hits with rule id, title, severity, and match evidence.
    """
    hits: list[dict[str, Any]] = []
    for hit, pat in _RULES:
        for m in pat.finditer(code):
            evidence = {
                "match": m.group(0)[:200],
                "start": m.start(),
                "end": m.end(),
            }
            hits.append(
                {
                    "rule_id": hit.rule_id,
                    "title": hit.title,
                    "severity": hit.severity,
                    "evidence": evidence,
                }
            )
    return hits

