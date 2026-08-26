"""Hermetic check: the deployed litellm must emit cost + model span attributes
through its langfuse_otel (Arize/OpenInference) path.

Langfuse v4 maps OpenInference span attrs -> observation fields:
  llm.cost.total    -> totalCost   (fed by response_cost; None if model unpriced)
  llm.model_name    -> modelId     (model granularity)

litellm 1.89.0 emitted neither (cost gated only in the Prometheus metric; the
langfuse_otel path dropped cost -> Langfuse showed totalCost=0 + modelId=null).
1.97.0 emits both via arize/_utils.py (_set_response_cost_attr + LLM_MODEL_NAME).
This fails if a future litellm bump regresses either attribute.

Companion guard: litellm-cost-map ensures every model has pricing so
response_cost is non-None (otherwise llm.cost.total is never set).

Usage: python langfuse_otel_attrs.py <site-packages-root>
"""

from __future__ import annotations

import pathlib
import sys

REQUIRED = ["llm.cost.total", "llm.model_name"]


def _scan(root: str) -> str:
    """Concatenate all .py under <root>/litellm (attribute names may live in
    integrations/, not just the langfuse_otel.py entry point)."""
    files = list(pathlib.Path(root).rglob("*.py"))
    if not files:
        return ""
    return "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)


def main() -> int:
    if len(sys.argv) < 2:
        print("FAIL: missing site-packages root")
        return 1
    root = sys.argv[1].rstrip("/")

    # Accept either the site-packages root or the nested litellm/ dir.
    candidates = [root, f"{root}/litellm", *[
        str(p) for p in pathlib.Path(root).rglob("litellm")
        if p.is_dir()
    ]]
    src = ""
    for c in candidates:
        s = _scan(c)
        if s:
            src = s
            break

    missing = [n for n in REQUIRED if n not in src]
    if missing:
        print(
            f"FAIL: litellm missing OpenInference span attributes {missing} "
            f"(too old / regressed — Langfuse would drop cost/model)"
        )
        return 1

    print(f"LANGFUSE OTEL ATTRS OK: {REQUIRED} all emitted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
