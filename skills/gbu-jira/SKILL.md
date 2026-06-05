---
name: gbu-jira
description: Use the Jira CLI to search, inspect, comment on, and update GBU Jira tickets with local config and token handling.
---

# GBU Jira CLI

Use the `jira` CLI for GBU Jira work.

- Reference: https://github.com/ankitpokhrel/jira-cli?tab=readme-ov-file
- Load local settings from `config/.env` if present. Use `config/.env.example` as the list of supported keys.

The Jira CLI owns site, user, and project defaults through the user's local CLI config. Prefer `~/.netrc` for authentication so `jira ...` works from normal shells and project contexts without sourcing skill-local env. Keep the ignored skill-local `.env` for config path, PAT expiry, and a fallback token only:

- `JIRA_CONFIG`
- `JIRA_API_TOKEN` (fallback only)
- `JIRA_PAT_EXPIRES_ON`

When creating or refreshing a PAT:

1. Add or update this entry in `~/.netrc`:
   ```text
   machine gbujira.oraclecorp.com
     login <oracle-email>
     password <PAT>
   ```
2. Run `chmod 600 ~/.netrc`.
3. Record the expiry date in `config/.env` as `JIRA_PAT_EXPIRES_ON`.
4. Verify with `jira issue view <issue-key> --plain` without setting `JIRA_API_TOKEN`.

Use `JIRA_API_TOKEN` from `config/.env` only as a fallback when `.netrc` is not configured or does not work.

## Onboarding

Use the simple setup path:

1. If `config/.env` is missing, run `scripts/onboard.py` and use the answers to create it.
2. If `config/.env` exists, assume setup is complete and skip preflight.
3. If execution fails because local setup is missing or invalid, run `scripts/onboard.py --repair`, then retry once when safe.
4. If running non-interactively, ask the user for missing values in chat and pass them with repeated `--set KEY=VALUE` arguments.
5. Keep `config/.env` and `config/local-learning.md` private; they are local runtime files, not shared skill content.

## Usage

- Use `--help` to find the relevant commands.
- Prefer read-only inspection commands unless the user explicitly asks for a change.
- PAT duration can vary. Check `JIRA_PAT_EXPIRES_ON` before assuming a token is expired.
- Run `jira ...` normally first so the CLI can use `~/.netrc`.
- If `.netrc` is missing or invalid, read `JIRA_API_TOKEN` from `config/.env` and pass it only for that Jira CLI invocation.

## Steps

1. If `config/.env` is missing, run onboarding before attempting CLI commands.
2. Once `config/.env` exists, invoke the CLI normally and let it authenticate through `~/.netrc`.
3. If the CLI fails because `.netrc` is missing or invalid, run `scripts/onboard.py --repair`, then retry once when safe.
4. If `.netrc` still fails and `JIRA_API_TOKEN` exists in `config/.env`, pass the token only for that Jira CLI invocation.
5. If the CLI fails because the token is expired or invalid, refresh the PAT token.
   - Confirm with the user before refreshing the token.
   - Using the Chrome DevTools MCP server, go to: `https://gbujira.oraclecorp.com/secure/ViewProfile.jspa`
   - Create a token named with today's date, for example: `codex_<YYYY-MM-DD>`.
   - Add or update the `gbujira.oraclecorp.com` entry in `~/.netrc`.
   - Run `chmod 600 ~/.netrc`.
   - Record the new token in `JIRA_API_TOKEN` only as a fallback.
   - Record the selected or displayed expiry date in `JIRA_PAT_EXPIRES_ON`.
   - Close the Chrome tab.
6. Verify with `jira issue view <issue-key> --plain` without setting `JIRA_API_TOKEN`.
7. Read `config/local-learning.md` if it exists, and use it only for this user's local/private Jira notes.
8. Capture reusable learning when the CLI path takes multiple attempts.

## Learning Loop

When multiple Jira CLI attempts fail before finding a working command shape:

1. Keep a short scratch trace of the intent, failed command shapes, error summaries, and the command that worked.
2. After success, decide whether the working pattern is reusable for future Jira work.
3. Prefer learning command-shape lessons and Jira CLI quirks, not one-off ticket facts.
4. Generalize commands with placeholders such as `$JIRA_CONFIG`, `$JIRA_API_TOKEN`, `<issue-key>`, `<project-key>`, and `<jql>`.
5. Never store secrets, tokens, raw command output, customer data, ticket details, or sensitive internal URLs in shared learnings.
6. Ask the user before adding or changing a learning.
7. Save broadly reusable, non-sensitive lessons in `## Learnings`.
8. Save private, user-specific notes in `config/local-learning.md`.
9. Remove or rewrite stale, duplicate, or misleading learnings when a better pattern is found.

## Learnings

- Prefer `~/.netrc` for Jira CLI authentication. Use `JIRA_API_TOKEN` from `config/.env` only as a fallback for a single invocation.
- If you get authentication errors such as 401, ask the user whether you should reset the token, then follow the steps above.
- If the token or expiry is missing from `config/.env`, run onboarding repair.
