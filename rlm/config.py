"""TOML / YAML config. Same keys, same types. Auth never lives in the file."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import yaml

from rlm.errors import ConfigError

HARD_MAX_PROMPT_TOKENS = 99_999
HARD_MAX_INSTRUCTIONS = 150
HARD_PROMPT_TOKEN_EXCLUSIVE = 100_000
DEFAULT_CELL_TIMEOUT_S = 300.0
TRACE_CAPTURE_PROFILES = frozenset({"metadata", "content"})

ALLOWED_ENVIRONMENTS = frozenset({"docker"})
FORBIDDEN_AUTH_KEYS = frozenset(
    {
        "openai_api_key",
        "api_key",
        "OPENAI_API_KEY",
        "openai_org_id",
        "OPENAI_ORG_ID",
        "openai_project",
        "OPENAI_PROJECT",
    }
)

_FIELD_NAMES = None


def _field_names() -> frozenset[str]:
    global _FIELD_NAMES
    if _FIELD_NAMES is None:
        _FIELD_NAMES = frozenset(f.name for f in fields(Config))
    return _FIELD_NAMES


@dataclass
class Config:
    root_model: str = "gpt-5"
    leaf_model: str = "gpt-5-mini"
    environment: str = "docker"
    max_depth: int = 16
    max_iterations: int = 30
    max_observation_chars: int = 3000
    max_prompt_tokens: int = HARD_MAX_PROMPT_TOKENS
    max_instructions: int = HARD_MAX_INSTRUCTIONS
    max_concurrent_subcalls: int = 8
    max_consecutive_errors: int = 5
    max_budget_usd: float | None = None
    max_timeout_s: float | None = None
    cell_timeout_s: float = DEFAULT_CELL_TIMEOUT_S
    log_dir: str = ".rlm/logs"
    verbose: bool = False
    trace_capture: str = "metadata"
    extra_instructions: list[str] | None = None
    architecture: str = "direct"
    planner_enabled: bool = False
    planner_max_selected: int = 16
    planner_max_leaf_calls: int = 16
    planner_max_child_calls: int = 8
    planner_shard_target_tokens: int = 12_000
    reduction_target_tokens: int = 12_000

    def __post_init__(self) -> None:
        from rlm.core.architecture import architecture_names

        if self.environment not in ALLOWED_ENVIRONMENTS:
            raise ConfigError(
                f"environment must be 'docker' (got {self.environment!r}). "
                "There is no in-process REPL; FakeEnv is tests-only."
            )
        if self.max_prompt_tokens > HARD_MAX_PROMPT_TOKENS:
            raise ConfigError(
                f"max_prompt_tokens cannot be raised above {HARD_MAX_PROMPT_TOKENS} "
                f"(got {self.max_prompt_tokens}). 100k or more input tokens is illegal."
            )
        if self.max_prompt_tokens < 1:
            raise ConfigError("max_prompt_tokens must be a positive int")
        if self.max_instructions > HARD_MAX_INSTRUCTIONS:
            raise ConfigError(
                f"max_instructions cannot be raised above {HARD_MAX_INSTRUCTIONS} "
                f"(got {self.max_instructions})."
            )
        if self.max_instructions < 1:
            raise ConfigError("max_instructions must be a positive int")
        if self.max_depth < 0:
            raise ConfigError("max_depth must be >= 0")
        if self.max_iterations < 1:
            raise ConfigError("max_iterations must be >= 1")
        if self.max_observation_chars < 32:
            raise ConfigError("max_observation_chars is too small")
        if self.max_concurrent_subcalls < 1:
            raise ConfigError("max_concurrent_subcalls must be >= 1")
        if self.max_consecutive_errors < 1:
            raise ConfigError("max_consecutive_errors must be >= 1")
        if self.max_budget_usd is not None and self.max_budget_usd < 0:
            raise ConfigError("max_budget_usd must be >= 0")
        if self.max_timeout_s is not None and self.max_timeout_s <= 0:
            raise ConfigError("max_timeout_s must be > 0")
        if self.cell_timeout_s <= 0:
            raise ConfigError("cell_timeout_s must be > 0")
        if self.trace_capture not in TRACE_CAPTURE_PROFILES:
            raise ConfigError("trace_capture must be 'metadata' or 'content'")
        if self.architecture not in architecture_names():
            choices = ", ".join(architecture_names())
            raise ConfigError(f"architecture must be one of: {choices}")
        # Compatibility for existing API calls and config files. Architecture is
        # now the authoritative selector; planned also keeps the old observable
        # config field truthful for callers that still inspect it.
        if self.planner_enabled and self.architecture == "direct":
            self.architecture = "planned"
        if self.architecture in {"planned", "planned_waves"}:
            self.planner_enabled = True
        for name in (
            "planner_max_selected",
            "planner_max_leaf_calls",
            "planner_max_child_calls",
            "planner_shard_target_tokens",
            "reduction_target_tokens",
        ):
            if getattr(self, name) < 1:
                raise ConfigError(f"{name} must be >= 1")
        if (
            self.architecture == "planned_waves"
            and self.planner_shard_target_tokens > self.max_prompt_tokens
        ):
            raise ConfigError("planner_shard_target_tokens cannot exceed max_prompt_tokens")
        if (
            self.architecture == "planned_waves"
            and self.reduction_target_tokens > self.max_prompt_tokens
        ):
            raise ConfigError("reduction_target_tokens cannot exceed max_prompt_tokens")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        raise ConfigError(f"{name} must be an int, got {type(value).__name__}")
    return value


def _as_float(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number, got {type(value).__name__}")
    return float(value)


def _as_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{name} must be a bool, got {type(value).__name__}")


def _as_str(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{name} must be a string, got {type(value).__name__}")
    return value


def _as_opt_float(name: str, value: Any) -> float | None:
    if value is None:
        return None
    return _as_float(name, value)


def _as_opt_str_list(name: str, value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ConfigError(f"{name} must be a list of strings")
    return list(value)


_COERCE = {
    "root_model": _as_str,
    "leaf_model": _as_str,
    "environment": _as_str,
    "max_depth": _as_int,
    "max_iterations": _as_int,
    "max_observation_chars": _as_int,
    "max_prompt_tokens": _as_int,
    "max_instructions": _as_int,
    "max_concurrent_subcalls": _as_int,
    "max_consecutive_errors": _as_int,
    "max_budget_usd": _as_opt_float,
    "max_timeout_s": _as_opt_float,
    "cell_timeout_s": _as_float,
    "log_dir": _as_str,
    "verbose": _as_bool,
    "trace_capture": _as_str,
    "extra_instructions": _as_opt_str_list,
    "architecture": _as_str,
    "planner_enabled": _as_bool,
    "planner_max_selected": _as_int,
    "planner_max_leaf_calls": _as_int,
    "planner_max_child_calls": _as_int,
    "planner_shard_target_tokens": _as_int,
    "reduction_target_tokens": _as_int,
}


def config_from_mapping(data: dict[str, Any]) -> Config:
    unknown = set(data) - _field_names() - FORBIDDEN_AUTH_KEYS
    if unknown:
        keys = ", ".join(sorted(unknown))
        raise ConfigError(f"Unknown config key(s): {keys}")
    auth = set(data) & FORBIDDEN_AUTH_KEYS
    if auth:
        raise ConfigError(
            "API keys must not appear in TOML/YAML. Set OPENAI_API_KEY in the environment."
        )
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in _COERCE:
            continue
        kwargs[key] = _COERCE[key](key, value)
    return Config(**kwargs)


def parse_config_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".toml":
        data = tomllib.loads(raw)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        raise ConfigError(f"Config file must be .toml, .yaml, or .yml (got {path})")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def discover_config_file(cwd: Path) -> Path | None:
    toml = cwd / "rlm.toml"
    yaml_files = [p for p in (cwd / "rlm.yaml", cwd / "rlm.yml") if p.is_file()]
    if toml.is_file() and yaml_files:
        raise ConfigError(
            "Found both rlm.toml and a YAML config in the current directory. "
            "Keep one format or pass --config <path>."
        )
    if len(yaml_files) > 1:
        raise ConfigError(
            "Found both rlm.yaml and rlm.yml. Keep one format or pass --config <path>."
        )
    if toml.is_file():
        return toml
    if yaml_files:
        return yaml_files[0]
    return None


def load_config(
    *,
    config_path: str | Path | None = None,
    cwd: str | Path | None = None,
    **overrides: Any,
) -> Config:
    """Precedence: kwargs / CLI, then --config or auto-discovered file, then defaults."""
    cwd_path = Path(cwd) if cwd is not None else Path.cwd()
    file_data: dict[str, Any] = {}
    if config_path is not None:
        file_data = parse_config_file(Path(config_path))
    else:
        found = discover_config_file(cwd_path)
        if found is not None:
            file_data = parse_config_file(found)
    merged = dict(file_data)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return config_from_mapping(merged)
