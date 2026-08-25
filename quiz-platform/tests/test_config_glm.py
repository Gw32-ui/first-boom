# -*- coding: utf-8 -*-
"""智谱配置回退：llm/vision 空配置自动补齐。"""
import app.config as cfg_mod


def test_load_config_zhipu_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "missing.yaml")
    monkeypatch.setattr(cfg_mod, "ENV_PATH", tmp_path / ".env")
    cfg = cfg_mod.load_config()
    assert cfg["vision"]["base_url"] == cfg_mod.ZHIPU_BASE_URL
    assert cfg["vision"]["model"] == cfg_mod.ZHIPU_MODEL
    assert cfg["llm"]["base_url"] == cfg_mod.ZHIPU_BASE_URL
    assert cfg["llm"]["model"] == cfg_mod.ZHIPU_MODEL


def test_load_config_reads_env_key(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "missing.yaml")
    env = tmp_path / ".env"
    env.write_text("ZHIPU_API_KEY=sk-test-123\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "ENV_PATH", env)
    cfg = cfg_mod.load_config()
    assert cfg["vision"]["api_key"] == "sk-test-123"
    assert cfg["llm"]["api_key"] == "sk-test-123"


def test_load_config_yaml_overrides(tmp_path, monkeypatch):
    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(
        "vision:\n  enabled: true\n  model: glm-4.7-flash\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", yaml_path)
    monkeypatch.setattr(cfg_mod, "ENV_PATH", tmp_path / ".env")
    cfg = cfg_mod.load_config()
    assert cfg["vision"]["enabled"] is True
    assert cfg["vision"]["model"] == "glm-4.7-flash"
    assert cfg["vision"]["base_url"] == cfg_mod.ZHIPU_BASE_URL
