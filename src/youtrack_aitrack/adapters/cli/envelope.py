"""Result envelope printed by ``claude -p --output-format json``.

Shape verified against Claude Code 2.1.318. Only the fields we consume are
modelled; everything else is ignored so newer CLI versions keep parsing.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from youtrack_aitrack.domain.agent_runner import AgentRunnerError


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    output_tokens: int = 0


class ResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: str = ""
    is_error: bool = False
    subtype: str | None = None
    total_cost_usd: float | None = None
    usage: Usage | None = None

    @property
    def input_tokens(self) -> int | None:
        """Prompt-side tokens including cache writes and reads.

        Raw ``input_tokens`` is a handful on a cached session while the cache
        fields carry the real context size; summing them is what a user means
        by "how big was the input".
        """
        if self.usage is None:
            return None
        u = self.usage
        return u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens

    @property
    def output_tokens(self) -> int | None:
        return None if self.usage is None else self.usage.output_tokens


def parse_result_envelope(stdout: str) -> ResultEnvelope | None:
    """Return the envelope, or None when stdout is not a JSON result object.

    Plain text (older CLI versions, test doubles) is passed through by the
    caller unchanged. A JSON object that claims ``type: result`` but fails
    validation is a real contract break and raises.
    """
    text = stdout.strip()
    if not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("type") != "result":
        return None
    try:
        return ResultEnvelope.model_validate(payload)
    except ValidationError as exc:
        raise AgentRunnerError(f"Claude Code CLI result envelope is malformed: {exc}") from exc
