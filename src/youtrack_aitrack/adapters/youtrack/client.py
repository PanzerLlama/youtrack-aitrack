"""YouTrackClient — REST adapter for field writes, comments, and activity polling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from youtrack_aitrack.adapters.youtrack.errors import YouTrackError
from youtrack_aitrack.domain.event import STATE_FIELD_NAME, IssueEvent

_ACTIVITY_FIELDS = (
    "id,timestamp,category(id),"
    "author(login),"
    "target(idReadable,project(shortName)),"
    "field(name,customField(name)),"
    "added(name),removed(name)"
)
_FIELD_METADATA_FIELDS = "id,$type,field(name)"
_DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class _FieldMeta:
    project_field_id: str
    issue_type: str


class YouTrackClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        project: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._project = project
        self._http = http or httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=_DEFAULT_TIMEOUT,
        )
        self._field_cache: dict[str, _FieldMeta] = {}

    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None:
        custom_fields: list[dict[str, Any]] = []
        for name, value in fields.items():
            meta = await self._resolve_field(name)
            custom_fields.append(_build_cf_payload(meta, value))
        url = f"{self._base}/api/issues/{issue_id}"
        payload = {"customFields": custom_fields}
        resp = await self._http.post(url, params={"fields": "id"}, json=payload)
        _check(resp)

    async def post_comment(self, issue_id: str, body: str) -> None:
        url = f"{self._base}/api/issues/{issue_id}/comments"
        resp = await self._http.post(url, params={"fields": "id"}, json={"text": body})
        _check(resp)

    async def changed_issues_since(self, cursor: str | None) -> tuple[list[IssueEvent], str | None]:
        params: dict[str, str] = {
            "categories": "CustomFieldCategory",
            "fields": _ACTIVITY_FIELDS,
            "reverse": "false",
        }
        if cursor is not None:
            params["cursor"] = cursor
        url = f"{self._base}/api/activitiesPage"
        resp = await self._http.get(url, params=params)
        _check(resp)
        data = resp.json()
        events = [
            ev
            for ev in (self._map_activity(act) for act in data.get("activities", []))
            if ev is not None
        ]
        next_cursor = data.get("afterCursor") or cursor
        return events, next_cursor

    def _map_activity(self, activity: dict[str, Any]) -> IssueEvent | None:
        target = activity.get("target") or {}
        project = (target.get("project") or {}).get("shortName")
        if project != self._project:
            return None
        field = activity.get("field") or {}
        custom_field = field.get("customField") or {}
        field_name = custom_field.get("name") or field.get("name") or ""
        from_value = _first_name(activity.get("removed"))
        to_value = _first_name(activity.get("added"))
        is_state = field_name == STATE_FIELD_NAME
        return IssueEvent(
            issue_id=target.get("idReadable") or "",
            project=project,
            event_kind="field_change",
            field_name=field_name,
            from_value=from_value,
            to_value=to_value,
            from_state=from_value if is_state else None,
            to_state=to_value if is_state else None,
            actor=(activity.get("author") or {}).get("login"),
            timestamp=_parse_timestamp(activity.get("timestamp")),
            raw=activity,
        )

    async def _resolve_field(self, name: str) -> _FieldMeta:
        if name in self._field_cache:
            return self._field_cache[name]
        url = f"{self._base}/api/admin/projects/{self._project}/customFields"
        resp = await self._http.get(url, params={"fields": _FIELD_METADATA_FIELDS})
        _check(resp)
        for entry in resp.json():
            entry_name = (entry.get("field") or {}).get("name")
            if not entry_name:
                continue
            self._field_cache[entry_name] = _FieldMeta(
                project_field_id=entry["id"],
                issue_type=_project_to_issue_type(entry["$type"]),
            )
        if name not in self._field_cache:
            raise YouTrackError(f"custom field not found in project {self._project!r}: {name!r}")
        return self._field_cache[name]


def _build_cf_payload(meta: _FieldMeta, value: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": meta.project_field_id, "$type": meta.issue_type}
    if meta.issue_type == "TextIssueCustomField":
        payload["value"] = {"text": value}
    elif meta.issue_type == "SimpleIssueCustomField":
        payload["value"] = value
    else:
        raise YouTrackError(
            f"unsupported custom field type {meta.issue_type!r}; only Simple/Text supported"
        )
    return payload


def _project_to_issue_type(project_type: str) -> str:
    if project_type.endswith("ProjectCustomField"):
        return project_type[: -len("ProjectCustomField")] + "IssueCustomField"
    return project_type


def _first_name(items: Any) -> str | None:
    if not items:
        return None
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            name = first.get("name")
            if isinstance(name, str):
                return name
    return None


def _parse_timestamp(raw: Any) -> datetime:
    if isinstance(raw, int | float):
        return datetime.fromtimestamp(raw / 1000.0, tz=UTC)
    raise YouTrackError(f"activity timestamp missing or non-numeric: {raw!r}")


def _check(resp: httpx.Response) -> None:
    if resp.is_success:
        return
    raise YouTrackError(
        f"YouTrack {resp.request.method} {resp.request.url}: {resp.status_code} {resp.text[:500]}"
    )
