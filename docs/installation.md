# Installation

## Requirements

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) for tool installation.
- Git CLI on `PATH` (used by the daemon to resolve branches and diff against
  your base branch).
- A YouTrack instance you can authenticate against (Cloud or self-hosted).
- An **agent backend** — at least one of:
  - **`anthropic_api`**: an Anthropic API key (SDK path, embedded-diff
    prompts, single request per action).
  - **`claude_code_cli`** *(recommended for production)*: the
    [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) on
    `PATH` plus, for daemon-friendly bare mode, an `ANTHROPIC_API_KEY`
    that the spawned `claude --bare -p` subprocess uses for auth.

You can configure both backends and pick per workflow / per action; see
[configuration.md](./configuration.md#agent-backends).

## Install the CLI

While in alpha:

```bash
uv tool install --from git+https://github.com/PanzerLlama/youtrack-aitrack youtrack-aitrack
```

This installs two equivalent entry points: `youtrack-aitrack` and the
shorter `yta` alias. Verify:

```bash
yta --help
yta --version          # or: yta version
```

To upgrade later:

```bash
uv tool install --from git+https://github.com/PanzerLlama/youtrack-aitrack youtrack-aitrack --force
```

## Scaffold the config directory

```bash
yta init
```

Creates `~/.youtrack-aitrack/` with `config.yaml`, a `.env.example`, and the
required `workflows/`, `prompts/`, `runs/` subdirectories. Override the
location with `--config-dir PATH` or `$YOUTRACK_AITRACK_HOME`.

## Provide secrets

```bash
cp ~/.youtrack-aitrack/.env.example ~/.youtrack-aitrack/.env
$EDITOR ~/.youtrack-aitrack/.env
```

Fill in:

```ini
YOUTRACK_URL=https://your-org.example.com/youtrack
YOUTRACK_TOKEN=perm:...
YOUTRACK_PROJECT=ABC
ANTHROPIC_API_KEY=sk-ant-...     # required for anthropic_api backend
                                  # and for claude_code_cli in bare mode
```

`ANTHROPIC_API_KEY` is consumed in two places: by the `anthropic_api`
backend for its SDK call, and by the `claude_code_cli` backend when running
in bare mode (it gets pushed into the spawned subprocess env so
`claude --bare -p` can authenticate without OAuth). Setting it once covers
both backends.

### Getting a YouTrack token

In YouTrack: avatar → **Profile** → **Account Security** tab → **New token**.
Scope `YouTrack` (read+write on your projects) is sufficient. The token
inherits your permissions, so for testing use your admin account; for
production, create a dedicated service-account user with scoped permissions.

### `YOUTRACK_URL` for JetBrains-hosted instances

For JetBrains-hosted YouTrack, the URL includes a `/youtrack` path suffix:

```
https://<workspace>.myjetbrains.com/youtrack
```

For self-hosted, use your YouTrack root URL (no path suffix typically).

## Add a workflow + prompts

`yta init` leaves `workflows/` and `prompts/` empty. The repository ships a
reference workflow you can copy as a starting point:

```bash
# Clone the source once (if you don't already have it)
git clone https://github.com/PanzerLlama/youtrack-aitrack /tmp/yta-source

cp /tmp/yta-source/workflows/ready-for-testing-audit.yaml ~/.youtrack-aitrack/workflows/
cp /tmp/yta-source/prompts/*.md ~/.youtrack-aitrack/prompts/
```

Then verify everything parses:

```bash
yta workflows list
yta workflows validate
```

## Set up YouTrack custom fields

The reference workflow writes to four custom fields. You need to create them
in YouTrack and attach them to your project before running it:

| Field name | Type |
|---|---|
| `Security Audit` | text |
| `Pages Changed` | text |
| `QA Plan` | text |
| `Audit Status` | string (simple) |

Field names are case-sensitive and must match exactly what's in the workflow
YAML. Only YouTrack `text` and `string` types are supported in v1 (no enum,
state, user, build, etc.).

## Pick a default backend

The fresh `config.yaml` from `yta init` sets:

```yaml
defaults:
  default_agent: anthropic_api    # SDK path; uses ANTHROPIC_API_KEY directly
```

For production daemon use, switch to the CLI agent backend in bare mode —
predictable per-call cost, no local CLAUDE.md/hook/plugin leakage into
prompts, agent inspects the working tree directly:

```yaml
defaults:
  default_agent: claude_code_cli
  cli_agent_mode: bare            # ANTHROPIC_API_KEY required; skips OAuth keychain
  cli_agent_concurrency: 1        # serialises CLI spawns; bump cautiously
  agent_timeout_seconds: 300      # per-action wall-clock cap
```

`cli_agent_mode: oauth` is the alternative — it reuses your local
`claude login` subscription. Useful for one-off interactive testing but
ill-suited to unattended daemons because the spawned `claude -p` re-loads
your global `~/.claude/CLAUDE.md`, project `CLAUDE.md`, hooks, plugins,
and MCP tool definitions on every invocation. That overhead silently
inflates request size and burns API TPM budget before the daemon prompt
content is even sent.

See [configuration.md](./configuration.md#agent-backends) for every option.

## First run

`cd` into a git repository where you have a feature branch matching the
default `branch_pattern: "{task_id}-*"`, then exercise the wiring without
spending agent tokens or touching YouTrack:

```bash
cd /path/to/your/repo
yta run <issue-id> --dry-run --stub-llm
```

Expected output is one row per action, all `ok`, ending with `DONE`. If you
see `skipped` rows or `BadParameter` errors, follow the troubleshooting
matrix in [operations.md](./operations.md).

## Next steps

See [operations.md](./operations.md) for the staircase of test commands that
moves you from stub runs all the way to daemon mode, and
[configuration.md](./configuration.md) for every config option.
