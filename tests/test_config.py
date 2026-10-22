import json
import os

import aurora_core.config as config


def test_settings_migrate_legacy_project_file_to_private_user_config(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    legacy = project / "aurora-settings.json"
    legacy_data = {"num_ctx": 3072, "weather_location": {
        "city": "Test City", "latitude": -21.2, "longitude": -50.8, "updated": 1,
    }}
    legacy.write_text(json.dumps(legacy_data), encoding="utf-8")
    private_dir = tmp_path / "config" / "aurora"
    monkeypatch.setattr(config, "APP_CONFIG", private_dir / "aurora-settings.json")
    monkeypatch.setattr(config, "LEGACY_APP_CONFIG", legacy)

    loaded = config.settings_load()

    assert loaded["num_ctx"] == 3072
    assert loaded["weather_location"] == legacy_data["weather_location"]
    assert json.loads(config.APP_CONFIG.read_text(encoding="utf-8")) == legacy_data
    assert legacy.read_text(encoding="utf-8") == json.dumps(legacy_data)
    assert os.stat(private_dir).st_mode & 0o777 == 0o700
    assert os.stat(config.APP_CONFIG).st_mode & 0o777 == 0o600


def test_settings_save_keeps_location_data_private(monkeypatch, tmp_path):
    private_dir = tmp_path / "config" / "aurora"
    monkeypatch.setattr(config, "APP_CONFIG", private_dir / "aurora-settings.json")
    monkeypatch.setattr(config, "LEGACY_APP_CONFIG", tmp_path / "missing.json")
    value = {"weather_location": {"latitude": 1.0, "longitude": 2.0}}

    config.settings_save(value)

    assert json.loads(config.APP_CONFIG.read_text(encoding="utf-8")) == value
    assert os.stat(config.APP_CONFIG).st_mode & 0o777 == 0o600
    assert not list(private_dir.glob("*.tmp"))


def test_settings_load_uses_defaults_when_json_root_is_not_an_object(monkeypatch, tmp_path):
    private_dir = tmp_path / "config" / "aurora"
    private_dir.mkdir(parents=True)
    path = private_dir / "aurora-settings.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "APP_CONFIG", path)
    monkeypatch.setattr(config, "LEGACY_APP_CONFIG", tmp_path / "missing.json")

    loaded = config.settings_load()

    assert loaded["model"] == config.DEFAULTS["model"]
