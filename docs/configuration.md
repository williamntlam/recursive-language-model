# Configuration

All tunables (models, depth, budgets, observation cap, log dir) can live in a **TOML or YAML** file. The two formats are equivalent: same keys, same types, same validation. Pick one.

Auth is **never** in the file.

## Discovery

When `config_path` / `--config` is omitted, `load_config` looks in the current working directory:

| File | Format |
|---|---|
| `rlm.toml` | TOML (`tomllib`) |
| `rlm.yaml` or `rlm.yml` | YAML (PyYAML) |

Rules:

- Exactly one family may exist. `rlm.toml` **and** a YAML file together → `ConfigError`.
- `rlm.yaml` **and** `rlm.yml` together → same error.
- `--config path` / `RLM.from_config(path)` skips discovery and loads that file.

Unknown keys are an error (not silently ignored). Type errors (string where int expected) are an error.

## Precedence

Later does **not** override earlier; the merge is:

1. Constructor kwargs / CLI flags (non-`None` values win)
2. `--config` / `from_config` file, **or** auto-discovered cwd file
3. Built-in defaults

`.env` is only for auth, loaded at process start, and does not override variables already in the environment.

## Auth (environment only)

Required:

```
OPENAI_API_KEY=sk-...
```

Optional: `OPENAI_ORG_ID`, `OPENAI_PROJECT`.

Ship `.env.example`; keep `.env` gitignored. These keys in TOML/YAML are rejected:

`openai_api_key`, `api_key`, `OPENAI_API_KEY`, `openai_org_id`, `OPENAI_ORG_ID`, `openai_project`, `OPENAI_PROJECT`.

Missing key → `StartupError` when constructing `OpenAIClient` (CLI exit `4`). `FakeClient` does not need a key.

## Keys

| Key | Default | Notes |
|---|---|---|
| `root_model` | `"gpt-5"` | Any RLM node (has a REPL), including the parent |
| `leaf_model` | `"gpt-5-mini"` | `llm_query` leaves |
| `environment` | `"docker"` | Only legal value. Anything else is `ConfigError` |
| `max_depth` | `16` | Nested `rlm_query` safety cap (`>= 0`) |
| `max_iterations` | `30` | Root loop cells (`>= 1`) |
| `max_observation_chars` | `3000` | Truncation of stdout shown to the model (`>= 32`) |
| `max_prompt_tokens` | `99999` | Hard max; smaller is allowed. Cannot exceed 99,999 |
| `max_instructions` | `150` | Hard max; smaller is allowed |
| `max_concurrent_subcalls` | `8` | Thread pool size for batched maps (`>= 1`) |
| `max_consecutive_errors` | `5` | Parse/REPL errors before abort (`>= 1`) |
| `max_budget_usd` | unset | Optional USD cap (`>= 0`) |
| `max_timeout_s` | unset | Optional wall-clock seconds for the whole run (`> 0`) |
| `cell_timeout_s` | `300` | Seconds before hung local Python in a cell is killed (`> 0`). Paused during `llm_query` / `rlm_query`. |
| `log_dir` | `".rlm/logs"` | Trajectory parent directory |
| `verbose` | `false` | Print iterations to stderr |
| `extra_instructions` | unset | List of strings; each counts as one instruction |
| `planner_enabled` | `false` | Opt in to deterministic scope + constrained plan execution for `ask` / `research` |
| `planner_max_selected` | `16` | Maximum manifest records a plan may select (`>= 1`) |
| `planner_max_leaf_calls` | `16` | Maximum planned leaf calls (`>= 1`) |
| `planner_max_child_calls` | `8` | Maximum planned target-enforced child calls (`>= 1`) |

Hard ceilings (cannot raise):

| Limit | Ceiling |
|---|---|
| Input tokens per LM call | `< 100,000` (`max_prompt_tokens` ≤ 99,999) |
| Instructions per LM call | `≤ 150` |

`RLM(max_prompt_tokens=100_000)` or `max_instructions=151` fails at `Config` construction.

`ASK_LEAF_CHARS` (24,000) is a code constant in `rlm/core/history.py`, not a config key. It decides `repo.ask` / `corpus.ask` leaf vs child. `max_observation_chars` (default 3000) is what keeps **parent** `hist` small.

## Examples

TOML (`rlm.toml`):

```toml
root_model = "gpt-5"
leaf_model = "gpt-5-mini"
environment = "docker"
max_depth = 16
max_iterations = 30
max_observation_chars = 3000
max_prompt_tokens = 99999
max_instructions = 150
max_concurrent_subcalls = 8
max_consecutive_errors = 5
# max_budget_usd = 2.00
# max_timeout_s = 120
cell_timeout_s = 300
log_dir = ".rlm/logs"
verbose = false
planner_enabled = false
```

YAML (`rlm.yaml`):

```yaml
root_model: gpt-5
leaf_model: gpt-5-mini
environment: docker
max_depth: 16
max_iterations: 30
max_observation_chars: 3000
max_prompt_tokens: 99999
max_instructions: 150
max_concurrent_subcalls: 8
max_consecutive_errors: 5
# max_budget_usd: 2.00
# max_timeout_s: 120
cell_timeout_s: 300
log_dir: .rlm/logs
verbose: false
planner_enabled: false
```

Checked-in templates: [`rlm.toml.example`](../rlm.toml.example), [`rlm.yaml.example`](../rlm.yaml.example).

## Extra instructions

`extra_instructions` is a list of additional rules counted toward the 150-instruction budget. They are composed into `PromptPayload.extra_rules` and **must not** grow mid-session. Prefer editing the prompt files under `rlm/prompts/` over stuffing long appendices here.
