"""Hermetic check: every model in _litellm.nix must be cost-resolvable.

litellm computes ``response_cost`` from ``model_prices_and_context_window_backup.json``,
keyed by the EXACT ``model`` string in ``litellm_params``. A custom-``api_base``
route like ``openai/MiniMax-M3`` is not in the map (only ``minimax/MiniMax-M3``
is), so its cost silently becomes ``None`` and the span carries no
``gen_ai.usage.cost`` -> Langfuse shows ``totalCost=0`` / ``modelId=null``.

This fails unless each model either (a) resolves by exact key in the price map,
or (b) declares explicit ``input_cost_per_token`` + ``output_cost_per_token`` in
its ``litellm_params`` block.

Usage: python litellm_cost_map.py <_litellm.nix> <litellm-package-root>
"""

from __future__ import annotations

import glob
import json
import re
import sys


def extract_models(nix_src: str) -> list[str]:
    """model = "..." lines that live inside a litellm_params block."""
    models: list[str] = []
    in_params = False
    for line in nix_src.splitlines():
        if "litellm_params" in line:
            in_params = True
        elif in_params and ("litellm_settings" in line or "router_settings" in line):
            in_params = False
        if in_params:
            m = re.search(r'model\s*=\s*"([^"]+)"', line)
            if m:
                models.append(m.group(1))
    return models


def block_has_explicit_cost(nix_src: str, model_str: str) -> bool:
    """Does the litellm_params block containing model_str set explicit pricing?"""
    idx = nix_src.find(f'model = "{model_str}"')
    if idx < 0:
        return False
    tail = nix_src[idx : idx + 1500]
    return "input_cost_per_token" in tail and "output_cost_per_token" in tail


def main() -> int:
    if len(sys.argv) < 3:
        print("FAIL: usage litellm_cost_map.py <_litellm.nix> <litellm-package-root>")
        return 1
    nix = open(sys.argv[1], encoding="utf-8").read()
    root = sys.argv[2].rstrip("/")
    json_candidates = glob.glob(
        f"{root}/lib/python*/site-packages/litellm/model_prices_and_context_window_backup.json"
    )
    if not json_candidates:
        print(f"FAIL: model_prices JSON not found under {root!r}")
        return 1
    with open(json_candidates[0], encoding="utf-8") as f:
        prices = json.load(f)

    models = extract_models(nix)
    if not models:
        print("FAIL: no litellm models found")
        return 1

    bad = []
    for m in models:
        exact = m in prices
        explicit = block_has_explicit_cost(nix, m)
        if not (exact or explicit):
            bad.append(m)

    if bad:
        for m in bad:
            print(
                f"FAIL: model {m!r} has no price-map entry AND no explicit "
                f"input/output_cost_per_token -> cost becomes None"
            )
        return 1

    print(f"LITELLM COST-MAP OK: {len(models)} models all cost-resolvable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
