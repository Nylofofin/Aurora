# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import hashlib

import pytest

from launchpad.aurora_launchpad_core import (
    MODEL_NAMES,
    OLLAMA_INSTALLER_SHA256,
    assess_environment,
    copy_existing_memory,
    format_size,
    missing_models,
    ollama_tags_response_ready,
    parse_ollama_models,
    reject_symlinks_in_tree,
    remove_owned_models,
    validate_ollama_installer,
)


def test_environment_accepts_only_fedora_workstation_gnome_wayland():
    os_release = {"ID": "fedora", "VARIANT_ID": "workstation", "PRETTY_NAME": "Fedora Workstation"}
    report = assess_environment(
        os_release,
        {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"},
        16 * 1024**3,
        20 * 1024**3,
    )
    assert report.supported
    assert not report.warnings


def test_environment_rejects_other_session_or_distribution():
    report = assess_environment(
        {"ID": "fedora", "VARIANT_ID": "workstation"},
        {"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "GNOME"},
        8 * 1024**3,
        20 * 1024**3,
    )
    assert not report.supported


def test_environment_warns_about_low_memory_and_disk():
    report = assess_environment(
        {"ID": "fedora", "VARIANT_ID": "workstation"},
        {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"},
        4 * 1024**3,
        5 * 1024**3,
    )
    assert report.supported
    assert len(report.warnings) == 2


def test_ollama_list_detects_only_missing_models():
    output = "NAME ID SIZE MODIFIED\ngemma3:1b-it-qat abc 815 MB 1 hour ago\n"
    assert parse_ollama_models(output) == {MODEL_NAMES[0]}
    assert missing_models(output) == (MODEL_NAMES[1],)


def test_uninstall_removes_only_recorded_launchpad_models(tmp_path: Path):
    manifest = tmp_path / "owned.txt"
    manifest.write_text("gemma3:1b-it-qat\nnot-a-model\n", encoding="utf-8")
    calls = []
    removed = remove_owned_models("/usr/bin/ollama", manifest, lambda command: calls.append(command))
    assert removed == [MODEL_NAMES[0]]
    assert calls == [["/usr/bin/ollama", "rm", MODEL_NAMES[0]]]
    assert not manifest.exists()


def test_size_format_is_readable():
    assert format_size(31 * 1024**2) == "31.0 MiB"


def test_migration_copies_memory_without_removing_legacy_file(tmp_path: Path):
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    memory = old_root / "aurora-memory.json"
    memory.write_text('{"preferences": []}', encoding="utf-8")
    assert copy_existing_memory(old_root, new_root)
    assert (new_root / "aurora-memory.json").read_text(encoding="utf-8") == memory.read_text(encoding="utf-8")
    assert memory.exists()
    assert not copy_existing_memory(old_root, new_root)


def test_ollama_installer_accepts_only_expected_digest():
    audited = b"#!/bin/sh\nprintf 'audited installer\\n'\n"
    digest = hashlib.sha256(audited).hexdigest()
    validate_ollama_installer(audited, digest)
    with pytest.raises(ValueError, match="mudou"):
        validate_ollama_installer(audited + b"# changed\n", digest)


def test_ollama_installer_rejects_invalid_or_oversized_content():
    with pytest.raises(ValueError, match="cabeçalho"):
        validate_ollama_installer(b"not a script", hashlib.sha256(b"not a script").hexdigest())
    too_large = b"#!/bin/sh\n" + b"x" * 1_000_000
    with pytest.raises(ValueError, match="limite"):
        validate_ollama_installer(too_large)


def test_privileged_installer_digest_is_pinned_to_reviewed_snapshot():
    assert OLLAMA_INSTALLER_SHA256 == "25f64b810b947145095956533e1bdf56eacea2673c55a7e586be4515fc882c9f"


def test_ollama_readiness_requires_success_bounded_json_tags_payload():
    assert ollama_tags_response_ready(200, b'{"models": []}')
    assert not ollama_tags_response_ready(503, b'{"models": []}')
    assert not ollama_tags_response_ready(200, b'{"models":')
    assert not ollama_tags_response_ready(200, b'{"models": {}}')
    assert not ollama_tags_response_ready(200, b" " * 65_537)


def test_install_tree_rejects_nested_symlinks(tmp_path: Path):
    tree = tmp_path / "aurora"
    nested = tree / "assets" / "audio"
    nested.mkdir(parents=True)
    (nested / "outside-link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="link simbólico"):
        reject_symlinks_in_tree(tree)
