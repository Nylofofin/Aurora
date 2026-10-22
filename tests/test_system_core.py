from pathlib import Path

import aurora
import aurora_core.system.files as system_files


def test_spoken_percentage_parses_digits_and_portuguese_words():
    assert aurora.spoken_percentage("aumente para 35 por cento") == 35
    assert aurora.spoken_percentage("volume em vinte e cinco por cento") == 25
    assert aurora.spoken_percentage("volume para cento e dez") is None


def test_natural_directory_resolves_standard_folder_names(monkeypatch, tmp_path):
    documents = tmp_path / "Documentos"
    documents.mkdir()
    monkeypatch.setattr(system_files, "xdg_user_directory", lambda kind: documents if kind == "DOCUMENTS" else tmp_path)
    assert aurora.resolve_natural_directory("na pasta de documentos") == documents
    assert aurora.resolve_natural_directory(str(documents)) == documents


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
