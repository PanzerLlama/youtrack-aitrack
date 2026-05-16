"""JinjaPromptRenderer — render prompt templates from disk via jinja2."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from youtrack_aitrack.domain.context import Context


class JinjaPromptRenderer:
    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir
        self._env = Environment(
            loader=FileSystemLoader(str(prompts_dir)),
            autoescape=False,
            keep_trailing_newline=True,
            undefined=StrictUndefined,
            auto_reload=False,
        )

    def render(self, template: str, ctx: Context) -> str:
        try:
            tmpl = self._env.get_template(template)
        except TemplateNotFound as exc:
            raise FileNotFoundError(
                f"prompt template not found: {self._prompts_dir / template}"
            ) from exc
        # ctx.issue.raw is the full YouTrack activity payload (attacker-influenced
        # custom field values, comment text, etc.). Strip it before rendering so a
        # template can't accidentally pass that content into the LLM prompt.
        dump = ctx.model_dump()
        if isinstance(dump.get("issue"), dict):
            dump["issue"].pop("raw", None)
        return tmpl.render(ctx=dump)
