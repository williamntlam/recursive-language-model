"""Configuration unit contracts."""

from pathlib import Path

import pytest

from rlm.config import Config, config_from_mapping, load_config, parse_config_file
from rlm.errors import ConfigError

TOML = """
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
max_budget_usd = 2.00
max_timeout_s = 120
log_dir = ".rlm/logs"
verbose = false
"""

YAML = """
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
max_budget_usd: 2.00
max_timeout_s: 120
log_dir: .rlm/logs
verbose: false
"""


def test_toml_and_yaml_load_equal(tmp_path: Path):
    t = tmp_path / "rlm.toml"
    y = tmp_path / "rlm.yaml"
    t.write_text(TOML, encoding="utf-8")
    y.write_text(YAML, encoding="utf-8")
    a = config_from_mapping(parse_config_file(t))
    b = config_from_mapping(parse_config_file(y))
    assert a == b
    assert a.max_budget_usd == pytest.approx(2.0)


def test_both_toml_and_yaml_in_cwd_is_error(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rlm.toml").write_text('root_model = "gpt-5"\n', encoding="utf-8")
    (tmp_path / "rlm.yaml").write_text("root_model: gpt-4o\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="both"):
        load_config()


def test_yaml_and_yml_together_is_error(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rlm.yaml").write_text("root_model: gpt-5\n", encoding="utf-8")
    (tmp_path / "rlm.yml").write_text("root_model: gpt-5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="both"):
        load_config()


def test_explicit_config_skips_discovery(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rlm.toml").write_text('root_model = "gpt-5"\n', encoding="utf-8")
    (tmp_path / "rlm.yaml").write_text("root_model: gpt-5\n", encoding="utf-8")
    chosen = tmp_path / "explicit.yaml"
    chosen.write_text("root_model: gpt-4.1\nmax_depth: 3\n", encoding="utf-8")
    cfg = load_config(config_path=chosen)
    assert cfg.root_model == "gpt-4.1"
    assert cfg.max_depth == 3


def test_kwargs_override_file(tmp_path: Path):
    path = tmp_path / "rlm.yaml"
    path.write_text("root_model: gpt-5\nmax_depth: 4\n", encoding="utf-8")
    cfg = load_config(config_path=path, max_depth=9)
    assert cfg.max_depth == 9
    assert cfg.root_model == "gpt-5"


def test_unknown_key_is_error(tmp_path: Path):
    path = tmp_path / "rlm.toml"
    path.write_text('root_model = "gpt-5"\nunknown_thing = 1\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="Unknown"):
        load_config(config_path=path)


def test_type_error_is_config_error(tmp_path: Path):
    path = tmp_path / "rlm.yaml"
    path.write_text("max_depth: not-a-number\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="int"):
        load_config(config_path=path)


def test_openai_key_in_file_rejected(tmp_path: Path):
    path = tmp_path / "rlm.yaml"
    path.write_text("OPENAI_API_KEY: sk-secret\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="API key"):
        load_config(config_path=path)


def test_raising_ceilings_in_file_is_error(tmp_path: Path):
    path = tmp_path / "rlm.toml"
    path.write_text("max_prompt_tokens = 100000\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="max_prompt_tokens"):
        load_config(config_path=path)


def test_environment_local_rejected():
    with pytest.raises(ConfigError, match="docker"):
        Config(environment="local")


def test_cell_timeout_from_file(tmp_path: Path):
    path = tmp_path / "rlm.toml"
    path.write_text("cell_timeout_s = 90\n", encoding="utf-8")
    cfg = load_config(config_path=path)
    assert cfg.cell_timeout_s == pytest.approx(90.0)


def test_cell_timeout_must_be_positive():
    with pytest.raises(ConfigError, match="cell_timeout_s"):
        Config(cell_timeout_s=0)


def test_architecture_selects_planned_and_preserves_planner_alias():
    cfg = Config(architecture="planned")
    assert cfg.architecture == "planned"
    assert cfg.planner_enabled is True
    assert Config(planner_enabled=True).architecture == "planned"


def test_planned_waves_is_explicit_and_keeps_planner_compatibility():
    cfg = Config(architecture="planned_waves", planner_shard_target_tokens=8_000)
    assert cfg.architecture == "planned_waves"
    assert cfg.planner_enabled is True


def test_unknown_architecture_is_rejected():
    with pytest.raises(ConfigError, match="architecture"):
        Config(architecture="unbounded")
