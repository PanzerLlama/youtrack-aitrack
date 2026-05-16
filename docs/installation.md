# Installation

## Requirements

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/) for tool installation.
- Git CLI on `PATH` (used by the daemon to resolve branches and diff against
  your base branch).
- A YouTrack instance you can authenticate against (Cloud or self-hosted).
- An Anthropic API key.

## Install the CLI

While in alpha:

```bash
uv tool install --from git+https://github.com/PanzerLlama/youtrack-aitrack youtrack-aitrack
```

This installs two equivalent entry points: `youtrack-aitrack` and the
shorter `yta` alias. Verify:

```bash
yta --help
yta version
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
ANTHROPIC_API_KEY=sk-ant-...
```

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

## First run

`cd` into a git repository where you have a feature branch matching the
default `branch_pattern: "{task_id}-*"`, then exercise the wiring without
spending API tokens or touching YouTrack:

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
