"""Backwards-compat shim — re-exports the MiniMax-M3 helpers that used
to live here.

The implementation has moved to ``nc_ocr_flow.engines.minimax_engine``;
this module re-exports the per-page entry point and the helpers that
were used by other modules (and the existing test suite) under their
original names so external imports keep working.
"""
from __future__ import annotations

from nc_ocr_flow.engines.minimax_engine import (
    ENGINE_NAME,                  # noqa: F401
    MINIMAX_URL,                  # noqa: F401
    MINIMAX_MODEL,                # noqa: F401
    LOW_CONF_FLOOR,               # noqa: F401
    OCR_PROMPT_TOKEN_COST,        # noqa: F401
    OCR_TOOLS,                    # noqa: F401
    PROMPT,                       # noqa: F401
    MiniMaxError,                 # noqa: F401
    ocr_page_minimax,             # noqa: F401
    _chat,                        # noqa: F401
    _blocks_from_toolcall,        # noqa: F401
    _html_table_to_text,          # noqa: F401
)

__all__ = [
    "ENGINE_NAME",
    "MINIMAX_URL",
    "MINIMAX_MODEL",
    "LOW_CONF_FLOOR",
    "OCR_PROMPT_TOKEN_COST",
    "OCR_TOOLS",
    "PROMPT",
    "MiniMaxError",
    "ocr_page_minimax",
    "_chat",
    "_blocks_from_toolcall",
    "_html_table_to_text",
]