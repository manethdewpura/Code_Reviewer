from __future__ import annotations

from tools.security_scanner import scan_security_risks


def test_security_scanner_hardcoded_password() -> None:
    code = "password='1234'\nprint('ok')\n"
    hits = scan_security_risks(code)
    titles = [h["title"].lower() for h in hits]
    assert any("hardcoded" in t and "password" in t for t in titles)


def test_security_scanner_eval() -> None:
    code = "x = eval(user_input)\n"
    hits = scan_security_risks(code)
    assert any(h["rule_id"] == "SEC003" for h in hits)

