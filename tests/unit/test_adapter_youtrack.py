"""Tests for the YouTrackClient REST adapter (no real network — respx)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from youtrack_aitrack.adapters.youtrack.client import YouTrackClient
from youtrack_aitrack.adapters.youtrack.errors import YouTrackError
from youtrack_aitrack.domain.actions.set_field import FieldWriter
from youtrack_aitrack.domain.actions.yt_comment import CommentPoster
from youtrack_aitrack.domain.event import STATE_FIELD_NAME

BASE_URL = "https://yt.example"
PROJECT = "DEMO"


def _accepts_field_writer(client: FieldWriter) -> FieldWriter:
    return client


def _accepts_comment_poster(client: CommentPoster) -> CommentPoster:
    return client


def _make_client() -> YouTrackClient:
    return YouTrackClient(BASE_URL, "test-token", project=PROJECT)


def _meta_response(entries: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json=entries)


def test_client_satisfies_field_writer_and_comment_poster() -> None:
    client = _make_client()
    assert _accepts_field_writer(client) is client
    assert _accepts_comment_poster(client) is client


@respx.mock(base_url=BASE_URL)
async def test_set_fields_posts_simple_field_payload(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=_meta_response(
            [
                {"id": "PF-1", "$type": "SimpleProjectCustomField", "field": {"name": "Owner"}},
            ]
        )
    )
    issue_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-1"})
    )

    client = _make_client()
    await client.set_fields("DEMO-1", {"Owner": "lech"})

    assert issue_route.called
    body = issue_route.calls.last.request.read().decode()
    assert '"id":"PF-1"' in body
    assert '"$type":"SimpleIssueCustomField"' in body
    assert '"value":"lech"' in body


@respx.mock(base_url=BASE_URL)
async def test_set_fields_uses_text_value_shape(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=_meta_response(
            [
                {
                    "id": "PF-2",
                    "$type": "TextProjectCustomField",
                    "field": {"name": "Security Audit"},
                },
            ]
        )
    )
    issue_route = respx_mock.post("/api/issues/DEMO-2").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-2"})
    )

    client = _make_client()
    await client.set_fields("DEMO-2", {"Security Audit": "report body"})

    assert issue_route.called
    body = issue_route.calls.last.request.read().decode()
    assert '"$type":"TextIssueCustomField"' in body
    assert '"text":"report body"' in body


@respx.mock(base_url=BASE_URL)
async def test_field_metadata_cached_across_calls(respx_mock: respx.MockRouter) -> None:
    meta_route = respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=_meta_response(
            [
                {"id": "PF-1", "$type": "SimpleProjectCustomField", "field": {"name": "Owner"}},
            ]
        )
    )
    respx_mock.post("/api/issues/DEMO-1").mock(return_value=httpx.Response(200, json={}))
    respx_mock.post("/api/issues/DEMO-2").mock(return_value=httpx.Response(200, json={}))

    client = _make_client()
    await client.set_fields("DEMO-1", {"Owner": "a"})
    await client.set_fields("DEMO-2", {"Owner": "b"})

    assert meta_route.call_count == 1


@respx.mock(base_url=BASE_URL)
async def test_post_comment_hits_comments_endpoint(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post("/api/issues/DEMO-1/comments").mock(
        return_value=httpx.Response(200, json={"id": "C-1"})
    )

    client = _make_client()
    await client.post_comment("DEMO-1", "hello")

    assert route.called
    body = route.calls.last.request.read().decode()
    assert '"text":"hello"' in body


@respx.mock(base_url=BASE_URL)
async def test_changed_issues_since_state_event_populates_state(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/api/activitiesPage").mock(
        return_value=httpx.Response(
            200,
            json={
                "afterCursor": "cur-2",
                "activities": [
                    {
                        "id": "A1",
                        "timestamp": 1_700_000_000_000,
                        "category": {"id": "CustomFieldCategory"},
                        "author": {"login": "alice"},
                        "target": {
                            "idReadable": "DEMO-1",
                            "project": {"shortName": PROJECT},
                        },
                        "field": {
                            "name": STATE_FIELD_NAME,
                            "customField": {"name": STATE_FIELD_NAME},
                        },
                        "added": [{"name": "Ready for testing"}],
                        "removed": [{"name": "In progress"}],
                    },
                ],
            },
        )
    )

    client = _make_client()
    events, cursor = await client.changed_issues_since(None)

    assert cursor == "cur-2"
    assert len(events) == 1
    ev = events[0]
    assert ev.event_kind == "field_change"
    assert ev.field_name == STATE_FIELD_NAME
    assert ev.from_value == "In progress"
    assert ev.to_value == "Ready for testing"
    assert ev.from_state == "In progress"
    assert ev.to_state == "Ready for testing"
    assert ev.actor == "alice"
    assert ev.issue_id == "DEMO-1"
    assert ev.project == PROJECT


@respx.mock(base_url=BASE_URL)
async def test_changed_issues_since_non_state_event_skips_state_fields(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/api/activitiesPage").mock(
        return_value=httpx.Response(
            200,
            json={
                "afterCursor": "cur-3",
                "activities": [
                    {
                        "id": "A2",
                        "timestamp": 1_700_000_500_000,
                        "category": {"id": "CustomFieldCategory"},
                        "author": {"login": "bob"},
                        "target": {
                            "idReadable": "DEMO-7",
                            "project": {"shortName": PROJECT},
                        },
                        "field": {
                            "name": "Priority",
                            "customField": {"name": "Priority"},
                        },
                        "added": [{"name": "Critical"}],
                        "removed": [{"name": "Normal"}],
                    },
                ],
            },
        )
    )

    client = _make_client()
    events, _ = await client.changed_issues_since("cur-2")

    assert len(events) == 1
    ev = events[0]
    assert ev.field_name == "Priority"
    assert ev.from_value == "Normal"
    assert ev.to_value == "Critical"
    assert ev.from_state is None
    assert ev.to_state is None


@respx.mock(base_url=BASE_URL)
async def test_changed_issues_since_passes_cursor_param(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get("/api/activitiesPage").mock(
        return_value=httpx.Response(200, json={"afterCursor": None, "activities": []})
    )

    client = _make_client()
    events, cursor = await client.changed_issues_since("cur-5")

    assert events == []
    assert cursor == "cur-5"
    assert route.calls.last.request.url.params["cursor"] == "cur-5"


@respx.mock(base_url=BASE_URL)
async def test_changed_issues_since_filters_out_other_projects(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/api/activitiesPage").mock(
        return_value=httpx.Response(
            200,
            json={
                "afterCursor": "cur-x",
                "activities": [
                    {
                        "id": "A3",
                        "timestamp": 1_700_000_000_000,
                        "target": {
                            "idReadable": "OTHER-1",
                            "project": {"shortName": "OTHER"},
                        },
                        "field": {"name": STATE_FIELD_NAME},
                        "added": [{"name": "Done"}],
                        "removed": [{"name": "Open"}],
                    },
                ],
            },
        )
    )

    client = _make_client()
    events, _ = await client.changed_issues_since(None)

    assert events == []


@respx.mock(base_url=BASE_URL)
async def test_get_issue_state_returns_current_state(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "customFields": [
                    {"name": "Priority", "value": {"name": "Normal"}},
                    {"name": STATE_FIELD_NAME, "value": {"name": "Ready for testing"}},
                ]
            },
        )
    )

    client = _make_client()
    state = await client.get_issue_state("DEMO-1")

    assert state == "Ready for testing"


@respx.mock(base_url=BASE_URL)
async def test_get_issue_state_returns_none_when_state_absent(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(
            200,
            json={"customFields": [{"name": "Priority", "value": {"name": "Normal"}}]},
        )
    )

    client = _make_client()
    assert await client.get_issue_state("DEMO-1") is None


@respx.mock(base_url=BASE_URL)
async def test_get_issue_state_returns_none_when_value_null(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(
            200,
            json={"customFields": [{"name": STATE_FIELD_NAME, "value": None}]},
        )
    )

    client = _make_client()
    assert await client.get_issue_state("DEMO-1") is None


@respx.mock(base_url=BASE_URL)
async def test_get_issue_state_raises_on_4xx(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/api/issues/DEMO-1").mock(return_value=httpx.Response(404, text="missing"))

    client = _make_client()
    with pytest.raises(YouTrackError, match="404"):
        await client.get_issue_state("DEMO-1")


@respx.mock(base_url=BASE_URL)
async def test_4xx_response_raises_typed_error(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=httpx.Response(403, text="forbidden")
    )

    client = _make_client()
    with pytest.raises(YouTrackError, match="403"):
        await client.set_fields("DEMO-1", {"Owner": "x"})


@respx.mock(base_url=BASE_URL)
async def test_unknown_field_raises_typed_error(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=_meta_response([])
    )

    client = _make_client()
    with pytest.raises(YouTrackError, match="not found"):
        await client.set_fields("DEMO-1", {"Missing": "x"})
