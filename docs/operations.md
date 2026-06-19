# Operations Guide

How to actually run `youtrack-aitrack` against a project. Read in order — each
section builds on the previous one.

## Two ways to dispatch a workflow

`yta` has two dispatch entrypoints, and one of them has a daemon mode:

| Command | When to use | What it does |
|---|---|---|
| `yta run <issue-id>` | Manual one-shot — debugging, reruns, on-demand audit | Queries YouTrack for the issue's current state, fabricates a `status_change` event, dispatches matching workflows once, exits. |
| `yta poll` | Manual one-shot polling pass | Reads cursor, fetches new activities from YouTrack, dispatches workflows for matching events, saves the cursor, exits. |
| `yta poll --daemon` | Long-running automation | Same as `yta poll`, but loops on `poll_interval_seconds` forever. Handles SIGINT/SIGTERM for clean shutdown. |

The two paths share all the same engine, runtime, and adapters. The only
difference is how the `IssueEvent` is produced (one fabricates from current
state; the other comes from the YouTrack activity feed).

## Safety modifiers

Both `yta run` and `yta poll` accept these flags. Combine freely.

| Flag | YouTrack writes | LLM calls | Idempotency dedup | Typical use |
|---|---|---|---|---|
| `--dry-run` | **no** | yes | yes | inspect what the LLM would produce without touching YouTrack |
| `--stub-llm` | yes | **no** (returns a marked placeholder) | yes | verify YouTrack wiring + field types without spending tokens |
| `--dry-run --stub-llm` | **no** | **no** | yes | exercise the full trigger → dispatch path with zero external side effects |
| `--force` | yes | yes | **no** (bypasses) | re-run on a previously-seen `(workflow, issue, state, commit_sha)` |
| `--workflow=NAME` | yes | yes | yes | only run one workflow file by name; useful when you have several |
| `--repo-dir=PATH` | n/a | n/a | n/a | override the git repo root (default: current working directory) |

`--dry-run` and `--stub-llm` are orthogonal. `--force` is independent of both.

## What a run shows

On an interactive terminal, `yta run` renders a live region while the
workflow executes: each action's state (pending → running → ok / fail /
skipped) with a running elapsed timer, so a multi-minute CLI-agent run never
looks hung. The live region clears on completion, leaving a final summary:

```
WORKFLOW                     ACTION              STATE     TIME  NOTE
ready-for-testing-audit      security_audit      ok       1m02s
ready-for-testing-audit      pages_changed       ok       48.0s
ready-for-testing-audit      qa_plan             ok       55.4s
=== ready-for-testing-audit: DONE
```

The `TIME` column is each action's wall-clock duration. When stdout is not a
terminal (pipes, CI, the daemon), the live region is skipped and only the
final summary prints — so logs stay clean.

## Recommended testing sequence

When you first set up the daemon against a new project, walk the staircase
below. Each step adds exactly one capability over the previous one, so when
something breaks you know which step introduced it.

```bash
# 0. Sanity check: config parses, workflows validate
yta workflows list
yta workflows validate

# 1. Trigger matching + dispatch wiring (no external side effects)
yta run <issue-id> --dry-run --stub-llm

# 2. YouTrack field writes (no LLM spend)
yta run <issue-id> --stub-llm --force

# 3. Real LLM, inspect output offline (no YouTrack writes)
yta run <issue-id> --dry-run --force

# 4. Full real run
yta run <issue-id> --force

# 5. Polling — set the cursor so subsequent polls only see new activity
yta poll

# 6. Daemon
yta poll --daemon
```

Between steps 1 and 2 the LLM output goes to `~/.youtrack-aitrack/runs/<date>/<run-id>.json`.
You can inspect it before letting the result land in YouTrack:

```bash
jq '.action_results[] | {action_id, output_text: (.output.text // "")[:200]}' \
  ~/.youtrack-aitrack/runs/*/*.json
```

## Daemon mode

```bash
cd <repo-with-feature-branches>
yta poll --daemon
```

The daemon runs in the foreground. Use `tmux`/`screen`/systemd unit/Docker
to background it. SIGINT (Ctrl-C) and SIGTERM trigger a clean exit at the
next poll boundary — in-flight dispatches finish before the loop quits.

`--interval-seconds N` overrides the configured poll interval (default 60).

Per iteration, the daemon emits one line:

```
poll: cursor 'X' -> 'Y' events=3 filtered=2 workflows_fired=1 actions_run=3
```

| Field | Meaning |
|---|---|
| `cursor X -> Y` | activity feed cursor before/after this iteration |
| `events` | activity records fetched from YouTrack |
| `filtered` | events dropped by `include_tags` (see below) |
| `workflows_fired` | distinct workflow runs dispatched |
| `actions_run` | total action invocations across all dispatched workflows |

## Scoping by tag

For testing against a shared production YouTrack instance, scope the daemon to
specific issues using `defaults.include_tags`:

```yaml
defaults:
  include_tags: [daemon-test]
```

In YouTrack, tag the issues you want the daemon to act on with `daemon-test`
(or whatever names you chose). Other issues are fetched but skipped before
dispatch (counted in the `filtered` column). Empty/absent `include_tags` means
process every event for the configured project — the default.

`yta run <issue-id>` always bypasses this filter. Manual runs are explicit user
intent.

## Idempotency

Every dispatch is keyed by `workflow_name|issue_id|to_state|commit_sha`. The
same key never dispatches twice. This means:

- Repeated state transitions for the same branch state and same commit ⇒ deduped.
- A new commit on the same branch ⇒ new key ⇒ new dispatch.
- The same workflow on the same state but a different workflow name ⇒ different key ⇒ dispatches.

`--force` bypasses the check. It re-dispatches even if the key has been seen.
Use it for: rerunning after editing a prompt, debugging a flaky LLM response,
or recovering from a botched run.

## Cost guidance

For the bundled reference workflow (3 Sonnet 4.6 calls per dispatch), each run
costs roughly a few cents at typical diff sizes (~5-50 KB of context). Cost
scales linearly with diff size — for large refactors with hundreds of KB of
diff, expect several dollars per run.

To bound cost:

- Keep your `branch_pattern` tight so only the issue's feature branch is
  diffed, not the entire repo.
- Use `--stub-llm` for any non-cost-sensitive testing — the wiring runs end
  to end but no Anthropic calls are made.
- Switch `model` to `claude-haiku-4-5-20251001` per action in the workflow
  YAML if cheaper analysis is acceptable.
- A pure diff-filter for excluding generated files and capping prompt size
  is implemented in `domain/diff_filter.py` but not yet exposed via the
  workflow YAML schema — track that work via the issue tracker.

## Troubleshooting

Symptoms we've seen in practice and what causes them:

| Symptom | Likely cause | Fix |
|---|---|---|
| `No matching workflows.` | Issue isn't in the configured `to_state`; or workflow YAML wasn't loaded; or no YAML files in `<config-dir>/workflows/` | Check `yta workflows list`; check issue state in YouTrack matches workflow trigger |
| All actions `skipped` with `missing inputs: ['git_diff']` | Branch couldn't be resolved (no matching branch) or diff failed (wrong base branch) | Run `git branch --list '<task-id>-*'` to confirm; set `defaults.git_base_branch` to your repo's actual default |
| `YouTrackError: custom field not found in project 'X': 'Y'` | The field doesn't exist on the project | Create it in YouTrack admin and attach to the project |
| `YouTrackError: unsupported custom field type 'EnumProjectCustomField'` | Field is the wrong type | v1 supports only `Simple` (string) and `Text` — recreate with one of those types |
| `GitDiffError: ambiguous branch match` | Multiple branches match the pattern | Delete stale branches or tighten `branch_pattern` |
| Daemon shows `events=0` indefinitely | First-poll lookback window missed your transitions, or token lacks activity-feed permission | Check `defaults.poll_lookback_seconds`; verify with a direct `curl` against `/api/activitiesPage` |
| Reports written but fields stay empty in YouTrack | Old version before output-sink fix shipped | Reinstall: `uv tool install --from git+... --force` |

## Security and trust assumptions

Before running this in a production environment, know what's trusted and
what isn't:

- **Run one daemon per host per instance.** Idempotency is tracked in a
  local JSON file with no inter-process locking. If two daemons (or one
  daemon plus a manual `yta run`) process the same event concurrently,
  you may get duplicate dispatches. The single-daemon model is the
  supported configuration.
- **AI report output is advisory, not authoritative.** Diffs are
  attacker-influenceable: anyone who can commit to a feature branch can
  insert prompt-injection content aimed at manipulating the generated
  audit/QA reports. The adapter framing reduces this risk but does not
  eliminate it. Reviewers should always verify findings against the
  diff itself before acting on them.
- **No safe-by-default for first runs.** `yta run` without flags will
  hit Anthropic (costs tokens) and write to YouTrack. Use the testing
  staircase above before pointing the daemon at production issues.
- **Per-issue field type support is narrow.** v1 supports YouTrack
  `Simple` (string) and `Text` field types only. Enum, state, user,
  build, and other types are rejected with a typed error.
- **Tokens never end up on disk.** The YouTrack token and Anthropic key
  are passed through HTTP headers only; they are not logged, not echoed
  in error messages, not included in run reports.

## Where to look for clues

- `~/.youtrack-aitrack/runs/<date>/*.json` — every dispatch leaves a full `RunReport` JSON with each action's input/output. Pretty-print with `jq`.
- `~/.youtrack-aitrack/runs/.cursor.json` — current polling cursor. Delete to re-replay from the lookback window.
- `~/.youtrack-aitrack/runs/.idempotency.json` — already-dispatched keys. Delete to allow re-runs without `--force` (irreversible — you'll re-pay for any LLM calls that fire).

See [configuration.md](./configuration.md) for every option's default and
type, and [workflows.md](./workflows.md) for the YAML schema.
