#!/usr/bin/env python3
"""Post-patch transform for litellm 1.97.0's custom_logger_registry.py.

litellm 1.97.0 unconditionally imports ~50 optional third-party observability
SDKs (boto3, agentops, braintrust, cloudzero, datadog, galileo, literalai, opik,
posthog, vantage, mlflow, newrelic, ...) at module level. nixpkgs ships litellm
with its `optional-dependencies` passthru empty, so the proxy crashes at import
on the first missing SDK. Rather than package ~50 SDKs (many absent from
nixpkgs), wrap each integration import in try/except and drop the unavailable
classes from the registry — mirroring litellm's own handling of its `enterprise`
loggers. Only configured callbacks (langfuse_otel -> opentelemetry) need their
deps present.

Usage: make_lazy.py <path-to-custom_logger_registry.py>
"""
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    src = f.read()

lines = src.split("\n")
out = []
i = 0
while i < len(lines):
    line = lines[i]
    m = re.match(r"^(from litellm\.integrations\.[A-Za-z0-9_.]+ import )(.*)$", line)
    if not m:
        out.append(line)
        i += 1
        continue
    stmt = line
    balance = stmt.count("(") - stmt.count(")")
    imports = [line]
    j = i + 1
    while balance > 0 and j < len(lines):
        stmt += "\n" + lines[j]
        balance += lines[j].count("(") - lines[j].count(")")
        imports.append(lines[j])
        j += 1
    names = re.findall(
        r"\bimport\s+([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)",
        stmt,
    )
    bind = []
    if names:
        for t in names[-1].split(","):
            bind.append(t.split()[-1])
    guarded = (
        "try:\n"
        + "\n".join("    " + ln for ln in imports)
        + "\nexcept ImportError:\n"
        + ("\n".join("    %s = None" % b for b in bind) if bind else "    pass")
    )
    out.append(guarded)
    i = j

new = "\n".join(out)
new = re.sub(
    r"(CALLBACK_CLASS_STR_TO_CLASS_TYPE\s*=\s*\{[^{}]*?\n\s*\})",
    r"\1\n    CALLBACK_CLASS_STR_TO_CLASS_TYPE = {"
    r"k: v for k, v in CALLBACK_CLASS_STR_TO_CLASS_TYPE.items() if v is not None}",
    new,
    count=1,
)
with open(path, "w", encoding="utf-8") as f:
    f.write(new)
print(f"patched {path}")
