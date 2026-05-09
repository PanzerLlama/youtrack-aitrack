"""Tests for OutputSpec discriminated union."""

import pytest
from pydantic import TypeAdapter, ValidationError

from youtrack_aitrack.domain.output import (
    CommentOutput,
    CustomFieldOutput,
    OutputSpec,
)

_OUTPUT_ADAPTER = TypeAdapter(OutputSpec)


def test_custom_field_output() -> None:
    o = CustomFieldOutput(name="QA Plan")
    assert o.kind == "custom_field"
    assert o.name == "QA Plan"


def test_comment_output_default() -> None:
    o = CommentOutput()
    assert o.kind == "comment"
    assert o.template is None


def test_output_spec_picks_custom_field() -> None:
    o = _OUTPUT_ADAPTER.validate_python({"kind": "custom_field", "name": "X"})
    assert isinstance(o, CustomFieldOutput)


def test_output_spec_picks_comment() -> None:
    o = _OUTPUT_ADAPTER.validate_python({"kind": "comment"})
    assert isinstance(o, CommentOutput)


def test_output_spec_unknown_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        _OUTPUT_ADAPTER.validate_python({"kind": "smoke_signal"})


def test_output_spec_missing_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        _OUTPUT_ADAPTER.validate_python({"name": "X"})
