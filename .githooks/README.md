# Repository Git hooks

This repository uses `.githooks` as its version-controlled Git hooks directory.
The local configuration command below activates it for a clone:

```bash
git config core.hooksPath .githooks
```

## `pre-push`

The pre-push hook examines each ref being pushed and blocks the push unless
the outgoing commits include a change to `CHANGELOG.md`. The changelog entry
must be under **Unreleased** and include a local `YYYY-MM-DD HH:MM TZ`
timestamp, as required by `AGENTS.md`.

Git permits an intentional emergency bypass with `git push --no-verify`; use it
only when the normal changelog requirement cannot be met.
