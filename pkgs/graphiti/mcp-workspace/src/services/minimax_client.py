"""MiniMax tool-calling OpenAI client.

MiniMax-M3 (and other reasoning models MiniMax serves) silently ignore
``response_format`` — ``json_schema`` returns fenced markdown, and ``json_object``
returns the wrong top-level key (e.g. ``facts`` instead of ``edges``). Their one
reliably-clean JSON path is function/tool calling: the model fills a JSON Schema
``arguments`` slot that the API validates, so the output cannot be fenced or
key-renamed.

This subclass overrides only ``_generate_response`` — the seam
``LLMClient._generate_response_with_retry`` calls — to emit ``tools`` +
``tool_choice`` instead of ``response_format``, then parse
``tool_calls[0].function.arguments``. Everything else (prompt injection,
tenacity retries, language instructions, cleanup) is inherited unchanged.

Divergence note: this depends on graphiti_core internals (``self.client`` as
AsyncOpenAI, the ``_generate_response`` seam, ``Message``). If graphiti_core
bumps and renames those, this module breaks loudly at import/first-call —
re-verify against the pinned version on any upgrade.
"""

from __future__ import annotations

import json
import typing

import openai
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, ModelSize
from graphiti_core.llm_client.errors import EmptyResponseError, RateLimitError
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.prompts.models import Message
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel


def _coerce_for_schema(value: typing.Any, schema: dict[str, typing.Any], defs: dict[str, typing.Any]) -> typing.Any:
    """Repair MiniMax-M3's two tool-calling manglings against the expected schema.

    MiniMax function-calling collapses single-element primitive arrays to an
    ``{"item": X}`` object and emits numeric scalars as strings (``"0"``). This
    walks ``value`` against ``schema`` (resolving ``$defs``) and repairs both,
    recursively. Object-typed arrays (``edges``, ``entities``) pass through
    structurally; only their scalar descendants are coerced.

    Anything already well-formed (or not covered by the schema) is returned
    unchanged, so this never corrupts a correct payload.
    """
    ref = schema.get('$ref')
    if ref:
        schema = defs.get(ref.split('/')[-1], schema)

    t = schema.get('type')

    if t == 'array':
        items = schema.get('items', {})
        if isinstance(value, dict) and 'item' in value:
            value = [value['item']]
        elif not isinstance(value, list):
            value = [value]
        return [_coerce_for_schema(v, items, defs) for v in value]

    if t == 'integer':
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return value
        return value

    if t == 'number':
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return value
        return value

    if t == 'object':
        props = schema.get('properties', {})
        if isinstance(value, dict):
            return {
                k: _coerce_for_schema(v, props.get(k, {}), defs)
                for k, v in value.items()
            }
        return value

    # string / boolean / null / unconstrained: pass through
    return value


class MiniMaxToolCallClient(OpenAIGenericClient):
    """OpenAIGenericClient that requests structured output via tool calling."""

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        # No schema → nothing to enforce via a tool; defer to the base path
        # (plain json_object / fenced-stripping behaviour).
        if response_model is None:
            return await super()._generate_response(messages, None, max_tokens, model_size)

        openai_messages: list[ChatCompletionMessageParam] = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role in ('user', 'system'):
                openai_messages.append({'role': m.role, 'content': m.content})

        schema = response_model.model_json_schema()
        tool_name = response_model.__name__
        tools: list[dict[str, typing.Any]] = [
            {
                'type': 'function',
                'function': {
                    'name': tool_name,
                    'description': schema.get(
                        'description', f'Extract {tool_name} information'
                    ),
                    'parameters': schema,
                },
            }
        ]
        tool_choice: dict[str, typing.Any] = {
            'type': 'function',
            'function': {'name': tool_name},
        }

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=self.temperature,
                max_tokens=max_tokens,
                tools=tools,  # type: ignore[arg-type]
                tool_choice=tool_choice,  # type: ignore[arg-type]
            )
        except openai.RateLimitError as e:
            raise RateLimitError from e

        message = response.choices[0].message
        if message.tool_calls:
            args = message.tool_calls[0].function.arguments
            try:
                data = json.loads(args)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f'Tool-call arguments were not valid JSON: {args!r}'
                ) from e
            return _coerce_for_schema(data, schema, schema.get('$defs', {}))

        # No tool_calls returned — fall back to plain text, matching base behaviour.
        content = message.content or ''
        if not content:
            raise EmptyResponseError('LLM returned an empty response')
        return _coerce_for_schema(
            json.loads(self._strip_code_fences(content)),
            schema,
            schema.get('$defs', {}),
        )
