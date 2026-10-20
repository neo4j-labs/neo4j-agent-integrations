"""Fill the policy templates from policy_facts.yaml and write data/policies/."""

from string import Template
from typing import Any

from graphrag_banking.config import POLICIES_DIR, POLICY_TEMPLATES_DIR
from graphrag_banking.facts import (
    all_rules,
    format_date,
    format_money,
    load_policy_facts,
    placeholder_key,
)

MONEY_FIELDS = ("amount", "threshold", "monthly_fee")
# Whole numbers, rendered as they are: 25, 5, 90.
NUMBER_FIELDS = ("hold_days", "percent", "years", "lookback_days", "min_red_flags")


def placeholder_values(facts: dict[str, Any]) -> dict[str, str]:
    """Map every ${placeholder} name to its rendered text."""
    values: dict[str, str] = {}
    for product in facts["products"]:
        code = product["product_code"]
        values[placeholder_key(code, "name")] = product["name"]
        values[placeholder_key(code, "monthly_fee")] = format_money(
            product["monthly_fee"]
        )
    for policy in facts["policies"]:
        code = policy["policy_id"]
        values[placeholder_key(code, "name")] = policy["name"]
        values[placeholder_key(code, "effective_date")] = format_date(
            policy["effective_date"]
        )
    for rule in all_rules(facts):
        code = rule["rule_code"]
        values[placeholder_key(code, "name")] = rule["name"]
        for field in MONEY_FIELDS:
            if rule.get(field) is not None:
                values[placeholder_key(code, field)] = format_money(rule[field])
        for field in NUMBER_FIELDS:
            if rule.get(field) is not None:
                values[placeholder_key(code, field)] = str(rule[field])
    return values


def render_policy(file_name: str, values: dict[str, str]) -> str:
    """Render one template. Raises KeyError naming any unknown placeholder."""
    template = Template((POLICY_TEMPLATES_DIR / file_name).read_text(encoding="utf-8"))
    return template.substitute(values)


def main() -> None:
    facts = load_policy_facts()
    values = placeholder_values(facts)
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    for policy in facts["policies"]:
        try:
            text = render_policy(policy["file"], values)
        except KeyError as err:
            raise SystemExit(f"{policy['file']}: unknown placeholder {err}") from err
        (POLICIES_DIR / policy["file"]).write_text(text, encoding="utf-8")
        print(f"Rendered {policy['file']}")


if __name__ == "__main__":
    main()
