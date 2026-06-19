# Configuration Reference

Every option `youtrack-aitrack` reads, where it comes from, and what the
default is. Pair this doc with `yta init`, which scaffolds a working
`config.yaml` and a `.env.example`.

## Where config lives

| Path | What |
|---|---|
| `~/.youtrack-aitrack/` | Default config directory. Override with `--config-dir` or `$YOUTRACK_AITRACK_HOME`. |
| `<config-dir>/config.yaml` | Main config (this document). |
| `<config-dir>/.env` | Secrets (auto-loaded via `python-dotenv` before any subcommand). |
| `<config-dir>/.env.example` | Template with required variable names. |
| `<config-dir>/workflows/` | YAML files describing each workflow. |
| `<config-dir>/prompts/` | Jinja templates referenced by `ai_report` actions. |
| `<config-dir>/runs/` | Run history, polling cursor, idempotency state. |

Precedence for config directory resolution: `--config-dir` flag → `$YOUTRACK_AITRACK_HOME` env var → `~/.youtrack-aitrack/`.

## Secret handling

`config.yaml` never holds secrets directly — it uses `${VAR}` references that
expand from the environment. Put the actual values in `.env`:

```ini
# .env
YOUTRACK_URL=https://your-org.youtrack.cloud/youtrack
YOUTRACK_TOKEN=perm:base64-string
YOUTRACK_PROJECT=ABC
ANTHROPIC_API_KEY=sk-ant-...
```

The CLI auto-loads `<config-dir>/.env` before every subcommand runs.
Variables left unset cause an explicit `WorkflowParseError` at startup —
the daemon fails fast rather than running with broken auth.

If a referenced variable isn't set, you'll see:

```
config.yaml: undefined environment variable ${YOUTRACK_TOKEN}
```

Add it to `.env` (or your shell environment) and retry.

## `config.yaml` reference

```yaml
youtrack:
  url: ${YOUTRACK_URL}
  token: ${YOUTRACK_TOKEN}
  project: ${YOUTRACK_PROJECT}

anthropic:
  api_key: ${ANTHROPIC_API_KEY}   # only used by claude_code_cli in bare mode

paths:
  workflows_dir: workflows
  prompts_dir: prompts
  runs_dir: runs

defaults:
  branch_pattern: "{task_id}-*"
  poll_interval_seconds: 60
  poll_lookback_seconds: 3600
  git_base_branch: main
  default_agent: claude_code_cli  # which AgentRunner backend to use when an action does not override
  agent_timeout_seconds: 300      # per-action wall-clock cap
  cli_agent_concurrency: 1        # shared semaphore size for all CLI-spawning backends
  cli_agent_mode: oauth           # 'bare' (API key auth, no local context loaded) | 'oauth' (uses claude login)
  # base_url: https://staging.example.com
  # include_tags: [daemon-test]
```

### `youtrack` section

| Field | Type | Default | Notes |
|---|---|---|---|
| `url` | string | required | Base URL up to but not including `/api`. For JetBrains-hosted instances this is `https://<workspace>.myjetbrains.com/youtrack`. For self-hosted, your YouTrack root. Trailing slash is stripped. |
| `token` | string | required | Permanent token in `perm:...` form. Get one from YouTrack: avatar → Profile → Account Security → New token. Scope `YouTrack` is sufficient. |
| `project` | string | required | Short name of the project (the prefix YouTrack uses in issue IDs). One daemon = one project. |

### `anthropic` section

| Field | Type | Default | Notes |
|---|---|---|---|
| `api_key` | string | required for `bare` mode | From `console.anthropic.com`. Stored in `.env`, expanded via `${ANTHROPIC_API_KEY}`. Used only by `claude_code_cli` when `cli_agent_mode: bare`; ignored in `oauth` mode. |

### `paths` section

| Field | Type | Default | Notes |
|---|---|---|---|
| `workflows_dir` | path | `workflows` | Relative to config dir. Every `*.yaml` in here is loaded at startup. |
| `prompts_dir` | path | `prompts` | Jinja templates resolved relative to this directory (NOT relative to the workflow YAML). |
| `runs_dir` | path | `runs` | Run logs, polling cursor, idempotency state land here. |

### `defaults` section

| Field | Type | Default | Notes |
|---|---|---|---|
| `branch_pattern` | string | `{task_id}-*` | Template for finding the git branch matching an issue. `{task_id}` is replaced with the issue ID before being passed to `git branch --list --all`. |
| `poll_interval_seconds` | int | `60` | Daemon sleep between polls. |
| `poll_lookback_seconds` | int | `3600` | First-poll window in seconds. On a fresh cursor, the daemon asks YouTrack for activity from `now - lookback`. Subsequent polls use the saved cursor. |
| `git_base_branch` | string | `main` | The base for `git diff --merge-base <base> <branch>`. Set to your repo's actual default branch (`master`, `develop`, etc.) if it isn't `main`. |
| `base_url` | string | `null` | Optional. When set, the `pages_changed` reference prompt instructs the LLM to prefix inferred routes with this URL to produce clickable links in the report. |
| `include_tags` | list[string] | `[]` (empty = no filter) | Daemon mode only: drop events whose issue doesn't have at least one of these YouTrack tags. Useful for scoping the daemon to a subset of issues on a shared instance. `yta run` bypasses this filter. |
| `default_agent` | string | `claude_code_cli` | Which `AgentRunner` backend to use when a workflow action does not set its own `agent:` field. `claude_code_cli` is the only shipping backend today (Phase 2 adds Codex / Gemini). See [agent backends](#agent-backends) for the contract it fulfils. |
| `agent_timeout_seconds` | int | `300` | Per-action wall-clock budget. The `AgentRunner` is given this as `timeout_s`; the CLI backend kills the spawned subprocess on overrun. |
| `cli_agent_concurrency` | int | `1` | Size of the `asyncio.Semaphore` shared across all CLI-spawning backends. `1` serialises every `claude -p` / `codex` / `gemini` spawn — safest default for rate-limit-sensitive accounts. Bump cautiously after measuring your provider's TPM budget. |
| `cli_agent_mode` | `bare` / `oauth` | `oauth` | How `claude_code_cli` authenticates its spawned subprocess. `bare` passes `--bare` and pushes `ANTHROPIC_API_KEY` into the subprocess env (no local CLAUDE.md, no hooks, no plugins — daemon-friendly). `oauth` reuses the user's `claude login` keychain and loads all local context (handy for interactive testing, NOT recommended for daemons). |

## Agent backends

Every `ai_report` action routes through an `AgentRunner` chosen by the
action's `agent:` field (or `defaults.default_agent` when unset). The
shipping registry:

| Backend name | Implementation | Auth | Behavior |
|---|---|---|---|
| `claude_code_cli` | `ClaudeCodeCliRunner` | `cli_agent_mode` (above) | Spawns `claude -p` per action with `cwd=<repo>`. Prompt should instruct the agent to inspect the commit via its own git/file tools; no diff embedded. |

`claude_code_cli` is the only backend that ships today. Phase 2 adds
further CLI backends (Codex / Gemini) under the same `AgentRunner`
Protocol — one adapter file each, registered alongside it.

A workflow action selects its backend with:

```yaml
- id: security_audit
  type: ai_report
  agent: claude_code_cli       # overrides default_agent for this action only
  prompt: security_audit_cli.md
  model: claude-sonnet-4-6     # optional; omit to use claude's own default model
```

Omit `agent:` to inherit `defaults.default_agent`. Passing an unknown name
fails at `wire()` time with the available backends listed. The per-action
`model:` is passed through to the spawned `claude -p`; when omitted, the CLI
falls back to claude's own default model.

### Picking an auth mode

`claude_code_cli` scales with PR size because the agent reads files on
demand through its own tools instead of receiving a diff inline. Requires
`claude` on `PATH`. Choose how it authenticates via `cli_agent_mode`:

- **`bare` (recommended for daemons)**: passes `--bare`, authenticates via
  `ANTHROPIC_API_KEY`, and skips local CLAUDE.md/hooks/plugins. The input is
  deterministic and predictable — and the agent still has full code context
  through its own file/git tools, so this is not a context-less path.
- **`oauth` (default)**: reuses your `claude login` subscription and bypasses
  the API org TPM tier. Loads your local CLAUDE.md/hooks/plugins on every
  spawn, which makes the input less predictable and inflates each request's
  size. Good for one-off interactive testing; ill-suited to unattended
  daemons.

## CLI override flags

A few options can be overridden per-invocation without editing config:

| Flag | Overrides | Applies to |
|---|---|---|
| `--config-dir PATH` | resolution of config directory | every subcommand |
| `--repo-dir PATH` | current working directory as git repo root | `run`, `poll` |
| `--interval-seconds N` | `defaults.poll_interval_seconds` | `poll --daemon` only |
| `--workflow NAME` | restricts to one workflow file | `run` |
| `--dry-run`, `--stub-llm`, `--force` | safety modifiers | `run`, `poll` |

## Validating your config

```bash
yta workflows validate      # parses every workflow YAML; non-zero exit on any failure
yta workflows list          # prints each workflow's name, trigger type, action count
```

`validate` does NOT make any network calls — it only checks YAML shape and
schema. To verify YouTrack credentials, run `yta run <issue-id> --dry-run --stub-llm`
on a real issue; it will hit `/api/issues/<id>` and surface auth errors.

## Reset state

| To clear | Delete |
|---|---|
| Polling cursor (re-replay from lookback) | `runs/.cursor.json` |
| Idempotency keys (allow re-dispatch without `--force`) | `runs/.idempotency.json` |
| Run history (free disk space) | `runs/YYYY-MM-DD/` directories |

Deletes are safe — the daemon recreates these files on demand.

See [operations.md](./operations.md) for how each option affects runtime
behavior, and [workflows.md](./workflows.md) for what the YAML files in
`workflows/` look like.
