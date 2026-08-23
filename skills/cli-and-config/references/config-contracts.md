# CLI and configuration contracts

- Configuration is TOML or YAML, never both through auto-discovery. Explicit
  `--config` bypasses discovery.
- Precedence is explicit CLI/API values, then selected or discovered config,
  then built-in defaults. Unknown keys and type mismatches fail loudly.
- Authentication comes only from environment variables or the gitignored
  `.env`; auth-shaped keys are rejected from configuration files.
- The only production environment is Docker. `FakeEnv` is test-only and must
  not become a CLI escape hatch.
- CLI exit classes are part of the user interface: budget/prompt failures 2,
  REPL exhaustion 3, and config/startup/input failures 4.

Read `docs/configuration.md` or `docs/cli.md` only for the surface you change.
