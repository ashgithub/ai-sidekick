# Development

## Validation

Run the full local validation pipeline:

```bash
./bin/sidekick-check
```

It runs:

1. `ruff check`
2. `compileall`
3. `pytest`

## Dead Code Audit

The current refactor removed these obsolete paths:

1. Deterministic tab/app skill routing path.
2. Resolved payload blob and synthetic execute-skill-with-payload prompt path.
3. Unused `preview_instruction` runtime API.
4. Unused deterministic `RouteError` export.
5. Unused `commands` config section in settings model.
