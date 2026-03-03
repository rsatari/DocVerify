"""
Cost Tracker — Global singleton that any agent can import and record API costs to.

Usage from any agent:
    from agents.cost_tracker import track_cost
    track_cost("answerer", "Q1", "claude-opus-4-6", input_tokens=5000, output_tokens=2000)

Usage from pipeline:
    from agents.cost_tracker import get_tracker
    get_tracker().print_summary()
"""

import threading


# Pricing per 1M tokens (input, output) — updated March 2026
PRICING = {
    # Anthropic
    "claude-opus-4-6":              {"in": 5.00,  "out": 25.00, "label": "Claude Opus 4.6"},
    "claude-sonnet-4-6":            {"in": 3.00,  "out": 15.00, "label": "Claude Sonnet 4.6"},
    "claude-sonnet-4-5-20250929":   {"in": 3.00,  "out": 15.00, "label": "Claude Sonnet 4.5"},
    # OpenAI
    "gpt-5.2":                      {"in": 2.50,  "out": 10.00, "label": "GPT-5.2"},
    "gpt-4o":                       {"in": 2.50,  "out": 10.00, "label": "GPT-4o"},
    "gpt-4o-mini":                  {"in": 0.15,  "out": 0.60,  "label": "GPT-4o-mini"},
    # Kimi
    "kimi-k2.5-0125":              {"in": 0.60,  "out": 3.00,  "label": "Kimi K2.5"},
    "kimi-k2.5":                   {"in": 0.60,  "out": 3.00,  "label": "Kimi K2.5"},
    # Google
    "gemini-3.1-pro-preview":      {"in": 1.25,  "out": 5.00,  "label": "Gemini 3.1 Pro"},
    "gemini-2.0-flash":            {"in": 0.10,  "out": 0.40,  "label": "Gemini 2.0 Flash"},
    "gemini-1.5-flash":            {"in": 0.075, "out": 0.30,  "label": "Gemini 1.5 Flash"},
}

DEFAULT_PRICING = {"in": 2.00, "out": 8.00, "label": "Unknown"}


class CostTracker:
    """Thread-safe global cost tracker."""

    def __init__(self):
        self._records = []
        self._lock = threading.Lock()

    def record(self, role: str, question_id: str, model: str,
               input_tokens: int, output_tokens: int):
        p = PRICING.get(model, DEFAULT_PRICING)
        cost = (input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000
        with self._lock:
            self._records.append({
                "role": role,
                "qid": question_id,
                "model": model,
                "in": input_tokens,
                "out": output_tokens,
                "cost": cost,
            })

    def reset(self):
        with self._lock:
            self._records.clear()

    def print_summary(self):
        with self._lock:
            records = list(self._records)

        if not records:
            print("\n  No API calls recorded.")
            return

        # Aggregate by role
        by_role = {}
        for r in records:
            key = r["role"]
            if key not in by_role:
                by_role[key] = {"model": r["model"], "in": 0, "out": 0, "cost": 0.0, "calls": 0}
            by_role[key]["in"] += r["in"]
            by_role[key]["out"] += r["out"]
            by_role[key]["cost"] += r["cost"]
            by_role[key]["calls"] += 1

        total_in = sum(v["in"] for v in by_role.values())
        total_out = sum(v["out"] for v in by_role.values())
        total_cost = sum(v["cost"] for v in by_role.values())

        sorted_roles = sorted(by_role.items(), key=lambda x: x[1]["cost"], reverse=True)

        print()
        print("  ┌──────────────────────┬──────────────────────┬────────────┬────────────┬──────────┐")
        print("  │ Role                 │ Model                │  Input Tok │ Output Tok │     Cost │")
        print("  ├──────────────────────┼──────────────────────┼────────────┼────────────┼──────────┤")

        for role, d in sorted_roles:
            label = PRICING.get(d["model"], {}).get("label", d["model"])
            if len(label) > 20:
                label = label[:19] + "…"
            calls = f" ({d['calls']}x)" if d["calls"] > 1 else ""
            role_str = f"{role}{calls}"
            if len(role_str) > 20:
                role_str = role_str[:19] + "…"
            print(f"  │ {role_str:<20} │ {label:<20} │ {d['in']:>10,} │ {d['out']:>10,} │ ${d['cost']:>6.4f} │")

        print("  ├──────────────────────┼──────────────────────┼────────────┼────────────┼──────────┤")
        print(f"  │ {'TOTAL':<20} │ {'':20} │ {total_in:>10,} │ {total_out:>10,} │ ${total_cost:>6.4f} │")
        print("  └──────────────────────┴──────────────────────┴────────────┴────────────┴──────────┘")
        print(f"  Estimated monthly cost (daily runs): ${total_cost * 30:.2f}")


# ── Global singleton ──
_tracker = CostTracker()


def get_tracker() -> CostTracker:
    return _tracker


def track_cost(role: str, question_id: str, model: str,
               input_tokens: int, output_tokens: int):
    """Convenience function — call from any agent."""
    _tracker.record(role, question_id, model, input_tokens, output_tokens)
