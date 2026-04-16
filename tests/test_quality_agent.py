from __future__ import annotations

from tools.complexity_tool import calculate_complexity


def test_complexity_tool_detects_complex_function() -> None:
    code = """
def f(x):
    if x == 1:
        return 1
    elif x == 2:
        return 2
    elif x == 3:
        return 3
    elif x == 4:
        return 4
    elif x == 5:
        return 5
    elif x == 6:
        return 6
    elif x == 7:
        return 7
    elif x == 8:
        return 8
    else:
        return 0
"""
    m = calculate_complexity(code, language="python")
    assert m["supported"] is True
    assert m["cyclomatic_max"] >= 5

