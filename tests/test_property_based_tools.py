from __future__ import annotations

import random
import string

from tools.complexity_tool import calculate_complexity
from tools.security_scanner import scan_security_risks


def _rand_ident(rng: random.Random, *, min_len: int = 3, max_len: int = 12) -> str:
    n = rng.randint(min_len, max_len)
    first = rng.choice(string.ascii_letters + "_")
    rest = "".join(rng.choice(string.ascii_letters + string.digits + "_") for _ in range(n - 1))
    return first + rest


def test_security_scanner_property_like_rules_trigger() -> None:
    """
    Property-style test (no Hypothesis dependency):
    For many randomized snippets, ensure each rule triggers when its pattern exists.
    """
    rng = random.Random(1337)
    rule_ids_seen: set[str] = set()

    # Run multiple rounds to catch brittle regexes.
    for _ in range(80):
        key = _rand_ident(rng)
        val = _rand_ident(rng) + str(rng.randint(0, 9999))

        snippets: list[tuple[str, str]] = [
            ("SEC001", f"{key} = 'ok'\npassword = '{val}'\n"),
            ("SEC002", f"q = \"SELECT * FROM users WHERE name='\" + {key}\n"),
            ("SEC003", f"{key} = eval(user_input)\n"),
            ("SEC004", "import pickle\nobj = pickle.loads(data)\n"),
            ("SEC005", "import subprocess\nsubprocess.run(cmd, shell=True)\n"),
        ]

        rule_id, code = rng.choice(snippets)
        hits = scan_security_risks(code)
        hit_ids = {h.get("rule_id") for h in hits}
        assert rule_id in hit_ids, f"Expected {rule_id} in hits; got {hit_ids}"
        rule_ids_seen.add(rule_id)

    # Sanity: across randomized runs we exercised all rules at least once.
    assert rule_ids_seen == {"SEC001", "SEC002", "SEC003", "SEC004", "SEC005"}


def test_complexity_tool_property_like_non_python_is_unsupported() -> None:
    rng = random.Random(4242)
    for _ in range(30):
        lang = rng.choice(["js", "ts", "java", "go", "ruby", "rust", "csharp"])
        out = calculate_complexity("function f() {}", language=lang)
        assert out["supported"] is False
        assert "reason" in out

