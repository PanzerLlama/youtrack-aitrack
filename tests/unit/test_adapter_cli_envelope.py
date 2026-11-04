"""parse_result_envelope — the JSON contract with `claude -p --output-format json`."""

from __future__ import annotations

import pytest

from youtrack_aitrack.adapters.cli.envelope import parse_result_envelope
from youtrack_aitrack.domain.agent_runner import AgentRunnerError


def test_plain_text_is_not_an_envelope() -> None:
    assert parse_result_envelope("## Findings\nNo issues.\n") is None


def test_json_that_is_not_a_result_object_is_ignored() -> None:
    assert parse_result_envelope('{"type":"assistant","message":"hi"}') is None
    assert parse_result_envelope("[1, 2]") is None
    assert parse_result_envelope("{not json") is None


def test_minimal_result_envelope_has_no_usage() -> None:
    env = parse_result_envelope('{"type":"result","result":"ok"}')
    assert env is not None
    assert env.result == "ok"
    assert (env.input_tokens, env.output_tokens, env.total_cost_usd) == (None, None, None)


def test_input_tokens_sum_cache_fields() -> None:
    env = parse_result_envelope(
        '{"type":"result","result":"","usage":{"input_tokens":2,'
        '"cache_creation_input_tokens":10,"cache_read_input_tokens":30,"output_tokens":4}}'
    )
    assert env is not None
    assert env.input_tokens == 42
    assert env.output_tokens == 4


def test_malformed_result_envelope_raises() -> None:
    with pytest.raises(AgentRunnerError, match="malformed"):
        parse_result_envelope('{"type":"result","usage":{"output_tokens":"many"}}')
