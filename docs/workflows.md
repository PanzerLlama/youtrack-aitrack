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

Never fires from the activity feed. Use for workflows you start on demand by
naming them explicitly:

```yaml
trigger:
  type: manual
```

```bash
yta run <issue-id> --workflow=<name>
```

`--workflow=NAME` bypasses trigger matching entirely (the name already says
which workflow you want), so a `manual` workflow runs regardless of the
issue's state. Idempotency still applies — pass `--force` to re-run for the
same issue. The poll/daemon path never bypasses triggers, so a `manual`
workflow can never fire unattended.

## Actions

Every action declares:

```yaml
- id: my_action            # required, unique within the workflow
  type: <action-type>      # required: ai_report | set_field | yt_comment | git_branch | write_file | bd_issue
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
| `task_meta` | The issue's summary, description and state could be fetched from YouTrack (`ctx.issue_details`). Unavailable only when that GET fails; the event fields (id, project, transition, actor, timestamp) are always present. |
| `route_index` | Reserved for future use; currently always unavailable. |
| `dependency_outputs` | Always (an action `depends_on` automatically receives upstream `ActionResult`s in context). |

Inputs are advisory — declaring `inputs: [git_diff]` doesn't fetch git_diff
specifically; it tells the engine "skip me if git_diff is unavailable". The
context-building lives in `Runner`, not in the action.

### Action types

#### `ai_report`

Renders a Jinja prompt template, sends it to the configured `AgentRunner`
backend, returns the text.

```yaml
- id: security_audit
  type: ai_report
  inputs: [git_diff]
  agent: claude_code_cli              # optional: per-action backend override
  output: { kind: custom_field, name: "Security Audit" }
  prompt: security_audit.md           # relative to prompts_dir
  model: claude-sonnet-4-6
```

| Field | Type | Notes |
|---|---|---|
| `prompt` | string | Path to a Jinja template, relative to `paths.prompts_dir`. |
| `model` | string | Model id. Passed verbatim to the backend — accepts whatever the chosen backend accepts (`claude-sonnet-4-6`, `claude-opus-4-7`, the `sonnet`/`opus`/`haiku` aliases for the CLI backend, etc.). |
| `agent` | string \| null | Backend name. Only `claude_code_cli` ships today (future `codex_cli` / `gemini_cli` arrive in Phase 2). Omit to inherit `defaults.default_agent`. Unknown names fail at runtime composition. |
| `mode` | `default` \| `plan` | `default` gives the agent its normal tools. `plan` runs it read-only (`--permission-mode plan` on the CLI backend): it explores the tree and its final message is the deliverable — use it for planning prompts that must not edit files. |
| `output` | OutputSpec | Where to write the agent's result. See below. |

The shipping backend is documented under
[configuration.md > Agent backends](./configuration.md#agent-backends).
The CLI backend gives the agent file-reading tools and no inline diff, so
prompts should reference `{{ ctx.commit_sha }}` and `{{ ctx.repo_path }}`
and instruct the agent to inspect the commit directly (see
`prompts/security_audit_cli.md` for the reference shape).

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

#### `git_branch`

Creates the issue's feature branch from a base branch and switches the
working tree to it. Idempotent: an existing branch is switched to instead of
recreated, so re-running a workflow is safe.

```yaml
- id: create_branch
  type: git_branch
  inputs: [task_meta]               # the slug needs the issue summary
  name: "{task_id}-{slug}"          # default
  base: main                        # default: defaults.git_base_branch
  checkout: true                    # default
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | Branch template. `{task_id}` is the issue id; `{slug}` is the issue summary folded to lowercase ASCII, hyphen-separated, cut on a word boundary at 40 chars (`PROJ-12-add-csv-export`). The default matches `defaults.branch_pattern`, so diff-based workflows find the branch later. |
| `base` | string \| null | Start point for a new branch. Omit to use `defaults.git_base_branch`. |
| `checkout` | bool | Switch to the branch after creating it. A switch is refused when tracked files have uncommitted changes (untracked files are fine); already being on the target branch always succeeds. |

The action fails when `{slug}` is needed but the summary is missing or
yields an empty slug, so it never creates a branch like `PROJ-12-`. Under
`--dry-run` no git command runs. The action's result carries
`output.branch` / `output.created` for downstream prompts and a one-line
`output.note` that `yta run` shows in the NOTE column.

#### `write_file`

Writes an upstream action's text output to a file inside the repository,
optionally committing it on the current branch.

```yaml
- id: save_plan
  type: write_file
  depends_on: [implementation_plan]
  source: implementation_plan                        # action id providing output.text
  path: "docs/plans/{task_id}.md"
  commit_message: "docs: implementation plan for {task_id}"   # omit to leave uncommitted
```

| Field | Type | Notes |
|---|---|---|
| `source` | string | Id of the action whose `output.text` is written (typically an `ai_report`). Fails if that action produced no text. |
| `path` | string | Relative path inside the repo; `{task_id}` is substituted. Absolute paths and `..` segments are rejected. Parent directories are created. |
| `commit_message` | string \| null | When set, only this file is staged and committed (`{task_id}` substituted). Other local changes stay untouched. |

Under `--dry-run` nothing is written or committed.

#### `bd_issue`

Persists an upstream action's text output as an issue in the target
project's [beads](https://github.com/steveyegge/beads) database, with a file
fallback for projects that don't use beads. Availability is decided
deterministically by the action — `bd` on `PATH` **and** a `.beads/`
directory in the repo — never by the agent.

```yaml
- id: track_plan
  type: bd_issue
  depends_on: [implementation_plan]
  source: implementation_plan                 # action id providing output.text
  title: "{task_id}: {summary}"               # default
  issue_type: feature                         # bd --type; default task
  priority: 2                                 # bd --priority; default 2
  external_ref: "{task_id}"                   # default; bd --external-ref
  fallback_path: "docs/plans/{task_id}.md"    # optional
  fallback_commit_message: "docs: implementation plan for {task_id}"   # optional
```

| Field | Type | Notes |
|---|---|---|
| `source` | string | Id of the action whose `output.text` becomes the issue body (`bd create --body-file -`). |
| `title` | string | `{task_id}` and `{summary}` (issue summary) are substituted. |
| `issue_type`, `priority` | string, int | Passed to `bd create --type` / `--priority`. |
| `external_ref` | string \| null | Passed to `--external-ref`; defaults to the YouTrack id so the two issues stay linked. |
| `fallback_path` | string \| null | When beads is unavailable, write the text here instead (same rules as `write_file.path`). Without it the action is **skipped**, not failed. |
| `fallback_commit_message` | string \| null | Commit the fallback file (`{task_id}` substituted). |

The result carries `output.tracker` (`beads` or `file`), `output.issue_id`
or `output.path`, and an `output.text` one-liner ("Implementation plan
tracked in beads as …") so you can add `output: { kind: comment }` to echo
where the plan landed. Under `--dry-run` availability is still detected but
no issue is created and no file written.

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
| `ctx.issue_details` | IssueDetails \| None | The issue's own content: `summary`, `description`, `state`. `None` when the YouTrack fetch failed (then `task_meta` is unavailable). Guard with `{% if ctx.issue_details %}`. |
| `ctx.branch` | str \| None | Branch resolved by `git branch --list <pattern>`. `None` if no branch matched. |
| `ctx.diff` | str \| None | `git diff --merge-base <base> <branch>`. `None` if branch unresolved or diff failed. Always present in context, but CLI-backend prompts typically ignore it (the agent reads the diff via its own tools). |
| `ctx.commit_sha` | str \| None | Tip commit of the resolved branch. CLI-backend prompts reference this when telling the agent which commit to inspect. |
| `ctx.repo_path` | Path \| None | Absolute path to the git repo root (from `--repo-dir` or cwd). CLI backends receive this as the spawned subprocess `cwd`; prompts mostly read it for paths-in-instructions. |
| `ctx.base_url` | str \| None | From `defaults.base_url`. Use to construct clickable URLs in reports. |
| `ctx.action_outputs` | dict[str, ActionResult] | Results of upstream actions (for `depends_on`). |

Jinja uses `StrictUndefined` — typos like `ctx.branche` will raise at render
time rather than silently producing empty strings. Always wrap optional
variables in `{% if %}` guards.

### Writing prompts

The CLI backend (`claude_code_cli`) gives the agent file-reading and shell
tools, with `cwd` set to `ctx.repo_path`. Prompts point the agent at the
commit and let it pull what it needs — no diff is embedded in the prompt:

```jinja
Inspect commit {{ ctx.commit_sha }} on branch {{ ctx.branch }} using
`git show` / `git diff` and targeted file reads. Output ONLY the markdown
report — no preamble.
```

The repo ships two CLI-style prompts as reference shapes:
`prompts/security_audit_cli.md` (audit a commit) and
`prompts/implementation_plan.md` (plan-mode: read the issue text, explore
the tree, output a plan). CLI variants of `pages_changed.md` and
`qa_plan.md` are a Phase 2 item.

## Validation

```bash
yta workflows validate         # exits 0 if all YAML files parse and validate
yta workflows validate -v      # prints each file's pass/fail status
```

Schema errors are reported with file path + line number where possible.

## Example: the plan-implementation workflow

The second shipped workflow (`workflows/plan-implementation.yaml`) is manual.
It starts work on a task: branch off, let the agent read the issue and the
code, and hand you a plan to discuss before anything is implemented.

```yaml
name: plan-implementation
trigger:
  type: manual
actions:
  - id: create_branch
    type: git_branch
    inputs: [task_meta]
    name: "{task_id}-{slug}"
  - id: implementation_plan
    type: ai_report
    inputs: [task_meta, dependency_outputs]
    depends_on: [create_branch]
    mode: plan
    output: { kind: comment }
    prompt: implementation_plan.md
    model: claude-sonnet-4-6
  - id: track_plan
    type: bd_issue
    depends_on: [implementation_plan]
    source: implementation_plan
    issue_type: feature
    fallback_path: "docs/plans/{task_id}.md"
    fallback_commit_message: "docs: implementation plan for {task_id}"
```

```bash
cd /path/to/your/repo
yta run PROJ-12 --workflow=plan-implementation --show-output
```

What happens: the branch `PROJ-12-<slug-of-summary>` is created from
`defaults.git_base_branch` and checked out (refused if tracked files have
uncommitted changes); the agent runs read-only in plan mode with the issue
summary and description in its prompt; the plan is posted as a comment on
the issue; then it is persisted in the project — as a beads issue
(external-ref `PROJ-12`) when the repo has `bd` + `.beads/`, otherwise
committed to `docs/plans/PROJ-12.md` on the new branch. `--show-output`
also prints it in the terminal. Prefer both beads and the file? Add a
`write_file` action next to `bd_issue`. Discuss and refine the plan
in an interactive `claude` session on that branch. To regenerate after
editing the issue, re-run with `--force` — the existing branch is reused.

## Example: the reference workflow

The repo ships a reference workflow (`workflows/ready-for-testing-audit.yaml`)
that exercises every feature above. Three parallel `ai_report` actions, one
declaring `depends_on` to chain after `pages_changed`, and `on_success`/`on_failure`
hooks that set an audit-status field. Copy it into your config dir as a
starting point and adapt the prompt templates to your project.

See [operations.md](./operations.md) for how dispatches actually run, and
[architecture.md](./architecture.md) for how to add a new trigger or action
type.
