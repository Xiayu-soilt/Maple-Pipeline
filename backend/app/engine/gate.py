DEFAULT_RULES = [
    {"metric": "pass_rate", "op": ">=", "threshold": 100.0, "name": "单测通过率"},
    {"metric": "coverage", "op": ">=", "threshold": 80.0, "name": "语句覆盖率"},
]

_OPS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
}


def _rules_from_config(cfg: dict) -> list[dict]:
    rules = []
    if "pass_rate_min" in cfg:
        rules.append({"metric": "pass_rate", "op": ">=", "threshold": float(cfg["pass_rate_min"]), "name": "单测通过率"})
    if "coverage_min" in cfg:
        rules.append({"metric": "coverage", "op": ">=", "threshold": float(cfg["coverage_min"]), "name": "语句覆盖率"})
    if "issues_max" in cfg:
        rules.append({"metric": "scan_issues", "op": "<=", "threshold": float(cfg["issues_max"]), "name": "安全风险数"})
    return rules or [dict(r) for r in DEFAULT_RULES]


def evaluate(gate_cfg: dict, metrics: dict | None) -> dict:
    """metrics 为空表示上游没有测试节点产出的指标，门禁直接放行并提示。"""
    rules = _rules_from_config(gate_cfg or {})
    checks = []
    if not metrics:
        return {
            "passed": True,
            "checks": [],
            "message": "未采集到上游测试指标，门禁按放行处理",
        }
    for rule in rules:
        actual = metrics.get(rule["metric"])
        if actual is None:
            checks.append({**rule, "actual": None, "passed": False})
            continue
        ok = _OPS.get(rule["op"], _OPS[">="])(actual, rule["threshold"])
        checks.append({**rule, "actual": actual, "passed": bool(ok)})
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "message": ""}
