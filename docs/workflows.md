# Workflow YAML Reference

A workflow is one YAML file in `<config-dir>/workflows/`. It declares exactly
one trigger and a sequence of actions to run when that trigger matches an
incoming `IssueEvent`. The engine reads every YAML on startup, validates it
against the pydantic schema, and routes matching events through the action
graph.

## Top-level shape

```yaml
name: ready-for-testing-audit          # required, unique within the directory
description: |                          # optional, free text
  Three parallel AI reports run when an issue moves to "Ready for testing"
  and write their results into Text custom fields.

trigger:                                # required, exactly one
  type: status_change
  to_state: "Ready for testing"
  from_state: "*"

actions:                                # required, ordered execution graph
  - id: security_audit
    type: ai_report
    inputs: [git_diff]
    output: { kind: custom_field, name: "Security Audit" }
    prompt: security_audit.md
    model: claude-sonnet-4-6

  # ...more actions...

on_success:                             # optional, fires when all actions DONE
  - id: mark_done
    type: set_field
    fields:
      "Audit Status": "done"

on_failure:                             # optional, fires when any action fails
  - id: mark_failed
    type: set_field
    fields:
      "Audit Status": "failed"
```

`name` must be unique across all loaded workflows. Action `id`s must be unique
within a single workflow.

## Triggers

Triggers are registered via decorator and matched against incoming events.
Two ship out of the box.

### `status_change`

Fires when the issue's State field transitions to a specific value.

```yaml
trigger:
  type: status_change
  to_state: "Ready for testing"   # required
  from_state: "In progress"        # optional; default "*" matches any
```

`from_state: "*"` (the default) skips the from-side check. Useful when you
want to react to any transition into the target state regardless of where
it came from.

### `manual`

Fires only when `yta run <issue-id>` fabricates a manual event. Use for
workflows you trigger on-demand rather than on state changes:

```yaml
trigger:
  type: manual
```

## Actions

Every action declares:

```yaml
- id: my_action            # required, unique within the workflow
  type: <action-type>      # required: ai_report | set_field | yt_comment
  depends_on: [other_id]   # optional list; this action waits for those
  inputs: [git_diff, ...]  # optional; declares what context this needs
  output:                  # optional; tells engine where to persist result
    kind: custom_field
    name: "Field Name"
  # ...type-specific fields...
```

### `inputs` and `unavailable_inputs`

Workflows declare what context each action needs via `inputs`. The runtime
computes which inputs are unavailable for the current dispatch (e.g.
`git_diff` is unavailable when no matching branch exists) and the engine
skips any action whose `inputs` overlap with the unavailable set. Skipped
actions don't fail the workflow; they cascade to actions that `depends_on`
them, so a downstream consumer of a skipped report is also skipped.

Recognised input names:

| Name | Available when |
|---|---|
| `git_diff` | Runner could resolve a branch and produce a diff. |
| `task_meta` | Always (issue id, project, transition, actor, timestamp). |
| `route_index` | Reserved for future use; currently always unavailable. |
| `dependency_outputs` | Always (an action `depends_on` automatically receives upstream `ActionResult`s in context). |

Inputs are advisory — declaring `inputs: [git_diff]` doesn't fetch git_diff
specifically; it tells the engine "skip me if git_diff is unavailable". The
context-building lives in `Runner`, not in the action.

### Action types

#### `ai_report`

Renders a Jinja prompt template, sends it to Anthropic, returns the text.

```yaml
- id: security_audit
  type: ai_report
  inputs: [git_diff]
  output: { kind: custom_field, name: "Security Audit" }
  prompt: security_audit.md           # relative to prompts_dir
  model: claude-sonnet-4-6
```

| Field | Type | Notes |
|---|---|---|
| `prompt` | string | Path to a Jinja template, relative to `paths.prompts_dir`. |
| `model` | string | Anthropic model id. Per-action override of `anthropic.default_model`. |
| `output` | OutputSpec | Where to write the LLM result. See below. |

#### `set_field`

Writes literal values to YouTrack custom fields.

```yaml
- id: mark_done
  type: set_field
  fields:
    "Audit Status": "done"
    "QA Status": "ready"
```

| Field | Type | Notes |
|---|---|---|
| `fields` | dict[str, str] | Field name → value. Field names are case-sensitive and must match the YouTrack project's custom field names. v1 supports `Simple` (string) and `Text` field types only. |

#### `yt_comment`

Posts a comment to the issue.

```yaml
- id: notify_qa
  type: yt_comment
  body: "Automated audit complete — see custom fields for the reports."
```

| Field | Type | Notes |
|---|---|---|
| `body` | string | Comment text. |

## OutputSpec

When an `ai_report` action declares `output:`, the engine writes the LLM's
result text to that sink after the action completes.

### `custom_field`

```yaml
output:
  kind: custom_field
  name: "Security Audit"
```

Writes the LLM output as the value of the named custom field (must be a Text
type field on the project).

### `comment`

```yaml
output:
  kind: comment
```

Posts the LLM output as a comment on the issue.

## `depends_on` and execution order

Actions without `depends_on` and with no skipped dependencies run in parallel
(via `asyncio.gather`). Actions with `depends_on` wait until those parents
complete before scheduling.

```yaml
actions:
  - id: pages_changed                 # runs immediately
    type: ai_report
    # ...

  - id: security_audit                # runs in parallel with pages_changed
    type: ai_report
    # ...

  - id: qa_plan                       # waits for pages_changed, runs after
    type: ai_report
    depends_on: [pages_changed]
    inputs: [dependency_outputs]
    # ...
```

A downstream action sees its parents' results in `ctx.action_outputs[parent_id]`
(a `dict[str, ActionResult]`), which the prompt template can read.

## `on_success` and `on_failure` hooks

Hooks are ordinary actions but run AFTER the main action graph completes:

- `on_success`: fires if no action in `actions` failed (skipped is fine).
- `on_failure`: fires if any action in `actions` failed, OR if the output-sink
  write failed.

Hooks themselves can use any action type. They can't declare `depends_on`
(they're a flat list, not a graph).

## Prompt template variables

`ai_report` actions render Jinja templates with a single root variable: `ctx`.
The template gets `ctx.model_dump()` so every nested field is accessible.

```jinja
- Issue: {{ ctx.issue.issue_id }} ({{ ctx.issue.project }})
- Branch: {{ ctx.branch }}
- Transition: {{ ctx.issue.from_state }} -> {{ ctx.issue.to_state }}

## Diff under review

```diff
{{ ctx.diff }}
```

{% if ctx.base_url -%}
Base URL: {{ ctx.base_url }}
{%- endif %}
```

Available variables:

| Variable | Type | Notes |
|---|---|---|
| `ctx.issue` | IssueEvent | `issue_id`, `project`, `event_kind`, `from_state`, `to_state`, `field_name`, `from_value`, `to_value`, `actor`, `timestamp`, `raw` |
| `ctx.branch` | str \| None | Branch resolved by `git branch --list <pattern>`. `None` if no branch matched. |
| `ctx.diff` | str \| None | `git diff --merge-base <base> <branch>`. `None` if branch unresolved or diff failed. |
| `ctx.base_url` | str \| None | From `defaults.base_url`. Use to construct clickable URLs in reports. |
| `ctx.action_outputs` | dict[str, ActionResult] | Results of upstream actions (for `depends_on`). |

Jinja uses `StrictUndefined` — typos like `ctx.branche` will raise at render
time rather than silently producing empty strings. Always wrap optional
variables in `{% if %}` guards.

## Validation

```bash
yta workflows validate         # exits 0 if all YAML files parse and validate
yta workflows validate -v      # prints each file's pass/fail status
```

Schema errors are reported with file path + line number where possible.

## Example: the reference workflow

The repo ships one reference workflow (`workflows/ready-for-testing-audit.yaml`)
that exercises every feature above. Three parallel `ai_report` actions, one
declaring `depends_on` to chain after `pages_changed`, and `on_success`/`on_failure`
hooks that set an audit-status field. Copy it into your config dir as a
starting point and adapt the prompt templates to your project.

See [operations.md](./operations.md) for how dispatches actually run, and
[architecture.md](./architecture.md) for how to add a new trigger or action
type.
