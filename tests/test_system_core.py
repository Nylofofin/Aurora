from pathlib import Path

import aurora
import aurora_core.system.files as system_files


def test_spoken_percentage_parses_digits_and_portuguese_words():
    assert aurora.spoken_percentage("aumente para 35 por cento") == 35
    assert aurora.spoken_percentage("volume em vinte e cinco por cento") == 25
    assert aurora.spoken_percentage("volume para cento e dez") is None


def test_volume_tool_handles_malformed_model_values_without_crashing(monkeypatch):
    import aurora_core.system.volume as volume

    calls = []
    monkeypatch.setattr(volume.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setattr(volume.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    assert "percentual inteiro" in volume.control_volume("set", "não é número")
    assert calls == []


def test_volume_status_reports_pipewire_errors_truthfully(monkeypatch):
    import aurora_core.system.volume as volume
    from types import SimpleNamespace

    monkeypatch.setattr(volume.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setattr(volume.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout="", stderr="No default sink"))
    assert volume.control_volume("status").endswith("No default sink")


def test_volume_up_caps_adjustment_at_100_percent(monkeypatch):
    import aurora_core.system.volume as volume
    from types import SimpleNamespace

    calls = []
    results = [SimpleNamespace(returncode=0, stdout="Volume: 0.980", stderr=""),
               SimpleNamespace(returncode=0, stdout="", stderr="")]
    monkeypatch.setattr(volume.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setattr(volume.subprocess, "run", lambda *args, **kwargs: (calls.append((args, kwargs)), results.pop(0))[1])

    assert volume.control_volume("up", 5) == "Volume aumentado para 100%."
    assert calls[1][0][0][-1] == "1.000"


def test_volume_up_does_not_mutate_when_current_volume_cannot_be_read(monkeypatch):
    import aurora_core.system.volume as volume
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr(volume.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setattr(volume.subprocess, "run", lambda *args, **kwargs: (calls.append(args), SimpleNamespace(returncode=1, stdout="", stderr="device unavailable"))[1])

    assert "não vou aumentá-lo" in volume.control_volume("up", 5)
    assert len(calls) == 1


def test_volume_subprocess_timeouts_are_reported_without_escaping(monkeypatch):
    import aurora_core.system.volume as volume

    monkeypatch.setattr(volume.shutil, "which", lambda _name: "/usr/bin/wpctl")
    monkeypatch.setattr(volume.subprocess, "run", lambda *_args, **_kwargs: (
        (_ for _ in ()).throw(volume.subprocess.TimeoutExpired("wpctl", 3))
    ))

    assert "tempo esgotado" in volume.control_volume("status")
    assert "não vou aumentá-lo" in volume.control_volume("up", 5)
    assert "tempo esgotado" in volume.control_volume("set", 35)


def test_natural_directory_resolves_standard_folder_names(monkeypatch, tmp_path):
    documents = tmp_path / "Documentos"
    documents.mkdir()
    monkeypatch.setattr(system_files, "xdg_user_directory", lambda kind: documents if kind == "DOCUMENTS" else tmp_path)
    assert aurora.resolve_natural_directory("na pasta de documentos") == documents
    assert aurora.resolve_natural_directory(str(documents)) == documents


def test_project_and_aurora_destinations_resolve_to_their_distinct_roots(monkeypatch, tmp_path):
    import aurora_core.system.files as files

    projects = tmp_path / "Projects"
    app_dir = projects / "aurora"
    monkeypatch.setattr(files, "APP_DIR", app_dir)

    assert aurora.resolve_natural_directory("pasta do projeto") == projects
    assert aurora.resolve_natural_directory("pasta da Aurora") == app_dir


def test_file_creation_never_overwrites_existing_file(tmp_path):
    destination = tmp_path / "safe.txt"
    destination.write_text("original", encoding="utf-8")

    try:
        aurora.create_user_file("safe.txt", str(tmp_path), "replacement")
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing file was overwritten")

    assert destination.read_text(encoding="utf-8") == "original"
