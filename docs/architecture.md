# Architecture

Hexagonal (ports & adapters) layout, ~2,000 lines of Python across 7 layers.
The point of the structure is that you can swap external systems (YouTrack,
Anthropic, git) without touching the domain or engine code, and you can add
a new trigger or action type as one file in the `domain/` tree.

## Layering

```
┌─ cli/ ────────────────────────────────────┐
│  ┌─ runtime/ ────────────────────────────┐│
│  │  ┌─ engine/ ────────────────────────┐ ││
│  │  │  ┌─ domain/ ──────────────────┐  │ ││
│  │  │  │  pydantic models           │  │ ││
│  │  │  │  Protocols                 │  │ ││
│  │  │  │  pure logic (no I/O)       │  │ ││
│  │  │  └────────────────────────────┘  │ ││
│  │  │  trigger matching                │ ││
│  │  │  action graph execution          │ ││
│  │  └──────────────────────────────────┘ ││
│  │  composition root                     ││
│  │  factory + runner + poller            ││
│  └────────────────────────────────────────┘│
│  Typer commands, argparse                  │
└────────────────────────────────────────────┘

     adapters/   ── implements domain Protocols, talks to I/O
     config/     ── YAML loaders, env expansion
     registry/   ── plugin name → class lookup
```

Hard rule: inner rings never import from outer rings. `domain` knows nothing
about `httpx`, `anthropic`, `subprocess`, or `jinja2`. The composition root
in `runtime/` is the only place that knows about every concrete adapter at
once.

## Each directory's job

### `domain/` — vocabulary, no I/O

Pure pydantic models and Protocol interfaces. Stdlib + pydantic only.

| File | Contains |
|---|---|
| `event.py` | `IssueEvent` |
| `context.py` | `Context` — what each action sees |
| `run.py` | `RunReport`, `ActionResult`, `RunState` |
| `workflow.py` | `Workflow` (top-level YAML schema) |
| `trigger.py` | `TriggerSpec` (data) + `Trigger` (Protocol) |
| `action.py` | `ActionSpec` (data) + `Action` (Protocol) |
| `output.py` | `OutputSpec` discriminated union + `OutputSink` Protocol |
| `inputs.py` | `GitDiffProvider` Protocol |
| `diff_filter.py` | Pure diff-trimming logic |
| `triggers/status_change.py`, `manual.py` | Concrete trigger types |
| `actions/ai_report.py`, `set_field.py`, `yt_comment.py` | Concrete action types |

### `engine/` — orchestration, still pure

The graph runner. Takes a workflow and an event, produces a `RunReport`.

| File | Contains |
|---|---|
| `engine.py` | `WorkflowEngine.dispatch`/`run`, `_execute_graph`, `_write_outputs` |
| `idempotency.py` | `IdempotencyStore` Protocol + key builder |
| `run_store.py` | `RunStore` Protocol |

### `adapters/` — I/O wrappers

Every Protocol from `domain/` is satisfied by exactly one adapter class.

| Adapter | Implements | What it does |
|---|---|---|
| `youtrack/client.py` | `FieldWriter`, `CommentPoster`, `IssueStateLookup`, `ActivityFeed`, `IssueTagsLookup` | httpx async REST client |
| `git/diff.py` | `GitDiffProvider` | `subprocess.run` wrapper around git CLI |
| `llm/anthropic.py` | `LLMClient` | wraps `anthropic.AsyncAnthropic` |
| `llm/jinja.py` | `PromptRenderer` | Jinja2 with `StrictUndefined` |
| `storage/runs.py` | `RunStore` + `IdempotencyStore` | atomic-write JSON files |

### `runtime/` — composition root

The only layer that knows about every concrete adapter at once.

| File | Contains |
|---|---|
| `factory.py` | `ActionFactory` (rebuilds ActionSpec instances with adapters injected), `StandardOutputSink`, NoOp/Stub adapters for `--dry-run`/`--stub-llm` |
| `runner.py` | `Wiring` dataclass, `wire()` helper, `Runner` class, `build_runner()` |
| `poller.py` | `Poller` class, `PollResult`, `build_poller()` |

### `cli/` — Typer commands

| File | Command(s) |
|---|---|
| `main.py` | root app, `--config-dir` resolution |
| `init.py` | `yta init` |
| `workflows.py` | `yta workflows list`/`validate` |
| `run.py` | `yta run <issue-id>` |
| `poll.py` | `yta poll [--daemon]` |

### `registry/`, `config/`

| Directory | Job |
|---|---|
| `registry/` | Decorator-based plugin name → class lookup for triggers and actions. |
| `config/` | YAML loaders for instance config + workflows; env-var expansion. |

## Key patterns

### Protocol over ABC

Everywhere a concrete adapter could vary, we use `typing.Protocol`:

```python
class FieldWriter(Protocol):
    async def set_fields(self, issue_id: str, fields: dict[str, str]) -> None: ...
```

Concrete classes match by shape, not inheritance. mypy `--strict` verifies
the conformance.

### Frozen pydantic models at every boundary

`Workflow`, `Context`, `RunReport`, `IssueEvent`, `InstanceConfig` are all
`frozen=True`. You can't mutate context mid-action; the engine builds a new
Context per batch with merged `action_outputs`.

### Discriminated subclass instantiation

`ActionSpec` has `type: str` and `extra="allow"`. The YAML loader reads
`type`, looks up the concrete class in the registry, instantiates with all
YAML fields. Each subclass declares a `Literal["ai_report"]`-style type
field for pydantic validation.

### Adapter injection via `PrivateAttr`

Each action subclass holds its adapter in a `PrivateAttr` (not serialized,
not in `model_dump()`). The loader produces specs with default no-op
adapters; `ActionFactory.materialize` swaps in the real ones at runtime
composition time.

### `unavailable_inputs` for graceful degradation

Workflows declare `inputs: [git_diff, task_meta]`. If `Runner` can't resolve
a branch, it passes `unavailable_inputs={"git_diff"}` to the engine. Actions
that declare a missing input get marked `skipped`. Downstream actions that
`depends_on` a skipped parent cascade-skip.

### Idempotency

`{workflow_name}|{issue_id}|{to_state}|{commit_sha}`. Same composite key
never dispatches twice; `--force` bypasses.

## Why engine-driven, not LLM-driven

`youtrack-aitrack` is deliberately NOT a YouTrack MCP server. An MCP server
hands YouTrack tools to an LLM and lets the LLM decide which tools to call,
in what order, in response to a human's natural-language request. That works
well for one-off "audit this issue" interactions but it's the wrong shape
for an autonomous daemon. Three concrete reasons motivate every key pattern
above:

**Determinism over flexibility.** A workflow YAML pins the action graph at
load time. The engine executes it the same way for every dispatch matching
the trigger. This is why actions are first-class data (`ActionSpec` pydantic
models) and the engine is pure Python — no LLM reasoning step lives between
"event arrives" and "actions run". An LLM-driven dispatch could choose
different actions each time, which is exactly what you want for interactive
help and exactly what you don't want for a daemon.

**Bounded cost per dispatch.** With idempotency keys and a pinned action
graph, you can predict the cost of one state transition: N `ai_report`
actions × diff size. An LLM choosing tools could, in principle, call
`get_issue` 50 times in a loop because it got confused. The `Action`
protocol's narrow API (`execute(ctx) -> ActionResult`) and the
output-sink convention (`output["text"]`) are what make the per-dispatch
cost legible.

**Auditable runs.** Every dispatch produces one `RunReport` JSON file with
every `ActionResult.output` recorded. You can `jq` over a year of runs to
answer "did the security_audit ever flag X?". A conversation log produced by
an LLM running tools is much harder to query — the structure is implicit.

The trade-off is: workflows must be expressible as a YAML graph. If your
need is "give Claude my YouTrack and let it figure things out on each
request", build (or use) a YouTrack MCP server — it's a better tool for
that job. The two could even coexist on the same instance: the daemon
handles state transitions autonomously, the MCP server handles interactive
asks. They don't compete; they solve different halves of the LLM-meets-YT
problem space.

A future MCP wrapper over `yta run` is plausible as a thin adapter — it
would let a human ask Claude "run the audit workflow on DEMO-42" via MCP
and have Claude shell out to the same `Runner.run(issue_id)` path the CLI
uses. The engine stays pinned; only the trigger surface widens.

## End-to-end trace: `yta poll --daemon` fires for an event

1. CLI (`cli/poll.py`) resolves config, calls `build_poller(config, config_dir)`.
2. `runtime/runner.py:wire` instantiates every adapter once. `ActionFactory` materializes each workflow's actions with real adapters.
3. `Poller.poll_loop` ticks every `poll_interval_seconds`.
4. `Poller.poll_once`: read cursor → `YouTrackClient.changed_issues_since(cursor)` → for each `IssueEvent`, check tag filter → `Runner.dispatch(event)`.
5. `Runner.dispatch` resolves branch + diff + commit_sha via `GitDiffAdapter`. Marks `git_diff` unavailable on failure.
6. `Engine.dispatch` filters workflows whose `Trigger.matches(event)` is True. Builds idempotency key per (workflow, event, commit_sha). Returns early for already-processed keys.
7. `Engine.run` per workflow: `_execute_graph` topologically schedules actions, batching independent ones via `asyncio.gather`. `Context(issue=event, branch, diff, base_url, action_outputs)` is built per batch.
8. Actions execute. `AiReportAction.execute` calls renderer + LLM. `SetFieldAction.execute` calls the writer.
9. `_write_outputs` walks each successful action's `OutputSpec` and calls the configured `OutputSink` (StandardOutputSink → YouTrack).
10. `on_success` or `on_failure` hooks run.
11. `JsonRunStore.save_run` persists the report; `mark_processed(key, run_id)` records idempotency.
12. `Poller` saves new cursor.

## Adding a new trigger type

1. Create `domain/triggers/<name>.py`:
   ```python
   @register_trigger("my_trigger")
   class MyTrigger(TriggerSpec):
       type: Literal["my_trigger"] = "my_trigger"
       # ...your YAML fields...

       def matches(self, event: IssueEvent) -> bool:
           # ...your logic...
   ```
2. Import it in `domain/triggers/__init__.py` so the decorator fires at import time.
3. Use `type: my_trigger` in workflow YAML.

That's it. No engine changes, no registry changes.

## Adding a new action type

1. Create `domain/actions/<name>.py`:
   ```python
   class MyAdapter(Protocol):
       async def do_thing(self, ...) -> ...: ...

   @register_action("my_action")
   class MyAction(ActionSpec):
       type: Literal["my_action"] = "my_action"
       # ...your YAML fields...

       _adapter: MyAdapter = PrivateAttr()

       def __init__(self, *, adapter: MyAdapter | None = None, **data: Any) -> None:
           super().__init__(**data)
           self._adapter = adapter if adapter is not None else _NoOpMyAdapter()

       async def execute(self, ctx: Context) -> ActionResult:
           result = await self._adapter.do_thing(...)
           return ActionResult(action_id=self.id, success=True, output={"text": result})
   ```
2. Import it in `domain/actions/__init__.py`.
3. Add a case to `runtime/factory.py:ActionFactory.materialize`:
   ```python
   case "my_action":
       return MyAction(**data, adapter=self._my_adapter)
   ```
4. Pass the concrete adapter into `ActionFactory(...)` in `runtime/runner.py:wire`.
5. If the action produces text that should be written to a sink, return
   `output={"text": ..., ...}` — `_write_outputs` looks for the `text` key.

## Adding a new adapter

Adapters live in `adapters/<system>/`. Each implements one or more Protocols
from `domain/`. Rules:

- One module per external system. Nothing else imports the SDK or subprocess.
- Raise a typed exception on errors (`YouTrackError`, `GitDiffError`, etc.)
  rather than letting underlying library exceptions leak through.
- Tests use `respx` for httpx-based adapters and tmp_path+real subprocess for git.

See [workflows.md](./workflows.md) for the YAML schema users write, and
[CLAUDE.md](../CLAUDE.md) for the project conventions enforced on every PR.
