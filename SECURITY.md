# Security Policy

## Supported versions

This project is currently in beta. Only the latest release line receives
security fixes.

| Version | Supported |
|---|---|
| 0.1.x (beta) | yes |
| < 0.1.0 (pre-beta) | no |

## Reporting a vulnerability

If you believe you've found a vulnerability in `youtrack-aitrack`, please
**do not open a public GitHub issue**. Instead, use GitHub's private
vulnerability reporting:

1. Open <https://github.com/PanzerLlama/youtrack-aitrack/security/advisories>.
2. Click **Report a vulnerability**.
3. Include:
   - A description of the issue
   - Reproduction steps (commands, config, the minimum repo state needed)
   - The affected version (`yta version`)
   - Any suggested fix or mitigation

You will receive an acknowledgement within 5 business days. We'll discuss
remediation timeline and embargo (if applicable) in the advisory thread.

## Threat model

The project ships with a documented threat model in [docs/operations.md](./docs/operations.md#security-and-trust-assumptions).
Issues that fall within the documented residual risks (e.g. prompt
injection in attacker-influenceable git diffs; cross-process idempotency
race when running multiple daemons) are accepted limitations — please
still report them so we can adjust the docs or implementation.

## What is in scope

- Code in `src/youtrack_aitrack/`, the shipped reference prompts in
  `prompts/`, and the reference workflow YAML in `workflows/`.
- The CLI entrypoints (`youtrack-aitrack`, `yta`) and their interaction
  with operator-supplied config, env, and YAML.

## What is out of scope

- Vulnerabilities in upstream dependencies (`anthropic`, `httpx`,
  `pyyaml`, `jinja2`, `pydantic`, `typer`) — report those to their
  respective projects. We'll bump the version constraint once a fix is
  available.
- Misconfiguration on the operator's side (e.g. running the daemon
  against a YouTrack token with more permissions than necessary).
- The Anthropic API and YouTrack REST API themselves.

## Coordinated disclosure

We aim to publish an advisory with a CVE assignment (where applicable)
once a fix lands in a tagged release. The advisory will credit the
reporter unless you ask to remain anonymous.
