import stat
import zipfile

import pytest

from aurora_core.system.archives import extract_zip_safely


def test_extracts_regular_zip_inside_destination(tmp_path):
    archive = tmp_path / "model.zip"
    destination = tmp_path / "extracted"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("model/final.mdl", b"model")

    extract_zip_safely(archive, destination)

    assert (destination / "model" / "final.mdl").read_bytes() == b"model"


@pytest.mark.parametrize("entry", ["../escape.txt", "/tmp/escape.txt", "model\\..\\escape.txt"])
def test_rejects_archive_path_traversal(tmp_path, entry):
    archive = tmp_path / "malicious.zip"
    destination = tmp_path / "extracted"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(entry, b"escape")

    with pytest.raises(ValueError, match="caminho de extração inválido"):
        extract_zip_safely(archive, destination)

    assert not (tmp_path / "escape.txt").exists()


def test_rejects_symlink_archive_entries(tmp_path):
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("model/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(info, "../../escape.txt")

    with pytest.raises(ValueError, match="tipo de entrada não permitido"):
        extract_zip_safely(archive, tmp_path / "extracted")


def test_rejects_oversized_archive_before_writing(tmp_path):
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("model/data", b"12345")

    with pytest.raises(ValueError, match="excede o limite"):
        extract_zip_safely(archive, tmp_path / "extracted", max_unpacked_bytes=4)


def test_refuses_nonempty_destination(tmp_path):
    archive = tmp_path / "model.zip"
    destination = tmp_path / "extracted"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep")
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("model/data", b"data")

    with pytest.raises(ValueError, match="precisa estar vazia"):
        extract_zip_safely(archive, destination)

    assert (destination / "keep.txt").read_text() == "keep"
