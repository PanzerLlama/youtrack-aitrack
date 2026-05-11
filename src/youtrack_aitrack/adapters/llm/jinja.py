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
        return tmpl.render(ctx=ctx.model_dump())
