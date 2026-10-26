# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import hashlib
import io
import tarfile

import pytest

from launchpad.aurora_launchpad_core import (
    MODEL_NAMES,
    OLLAMA_INSTALLER_SHA256,
    assess_environment,
    inspect_installation,
    is_official_github_download_url,
    latest_launchpad_update,
    newer_aurora_releases,
    copy_existing_memory,
    extract_release_tarball,
    format_size,
    missing_models,
    ollama_tags_response_ready,
    ollama_storage_creation_command,
    parse_ollama_models,
    prepare_first_boot_onboarding,
    schedule_personalization,
    reject_symlinks_in_tree,
    recommend_releases,
    remove_owned_models,
    validate_ollama_installer,
)


def test_first_install_onboarding_marker_preserves_private_user_settings(tmp_path):
    config = tmp_path / "config" / "aurora" / "aurora-settings.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"tts_voice":"pt-BR-ThalitaMultilingualNeural","num_ctx":2048}\n')

    assert prepare_first_boot_onboarding(config, "boot-1", existing_install=False)

    saved = __import__("json").loads(config.read_text())
    assert saved["tts_voice"] == "pt-BR-ThalitaMultilingualNeural"
    assert saved["num_ctx"] == 2048
    assert saved["onboarding_pending"] is True
    assert saved["onboarding_boot_id"] == "boot-1"
    assert "onboarding_session_id" in saved
    assert config.stat().st_mode & 0o777 == 0o600


def test_updating_existing_install_does_not_reschedule_first_run_wizard(tmp_path):
    config = tmp_path / "settings.json"
    config.write_text('{"keep":true}')
    assert not prepare_first_boot_onboarding(config, "boot-1", existing_install=True)
    assert __import__("json").loads(config.read_text()) == {"keep": True}


def test_schedule_personalization_preserves_existing_choices(tmp_path):
    config = tmp_path / "settings.json"
    config.write_text('{"assistant_name":"Luna","bubble_style":"emerald"}')
    assert schedule_personalization(config, "session-6")
    saved = __import__("json").loads(config.read_text())
    assert saved["assistant_name"] == "Luna"
    assert saved["bubble_style"] == "emerald"
    assert saved["onboarding_pending"] is True
    assert saved["onboarding_session_id"] == "reopen:session-6"


def test_installation_health_detects_stopped_service_as_repairable(tmp_path: Path):
    app = tmp_path / "aurora"
    app.mkdir()
    for name in ("aurora.py", "run.sh", "start-alpha.sh", "install-desktop.sh"):
        (app / name).write_text("# test", encoding="utf-8")
    unit = tmp_path / "aurora.service"
    unit.write_text(
        f"WorkingDirectory={app}\nExecStart={app}/start-alpha.sh\n",
        encoding="utf-8",
    )
    health = inspect_installation(app, unit, service_active=False)
    assert health.state == "repairable"
    assert health.repairable
    assert any("não está ativo" in detail for detail in health.details)


def test_installation_health_rejects_missing_payload(tmp_path: Path):
    health = inspect_installation(tmp_path / "missing", tmp_path / "aurora.service", service_active=False)
    assert health.state == "missing"
    assert not health.repairable


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


def test_ollama_storage_command_creates_missing_directory_with_service_owner(tmp_path: Path):
    path = tmp_path / "ollama"
    assert ollama_storage_creation_command(path, service_uid=991, service_gid=991) == [
        "/usr/bin/install", "-d", "-o", "991", "-g", "991", "-m", "0755", str(path)
    ]


def test_ollama_storage_existing_directory_must_have_expected_owner(tmp_path: Path):
    path = tmp_path / "ollama"
    path.mkdir()
    if path.stat().st_uid == 12345 or path.stat().st_gid == 12345:
        pytest.skip("Test owner coincides with host account.")
    with pytest.raises(ValueError, match="proprietário inesperado"):
        ollama_storage_creation_command(path, service_uid=12345, service_gid=12345)
    assert ollama_storage_creation_command(
        path, service_uid=path.stat().st_uid, service_gid=path.stat().st_gid
    ) is None


def test_ollama_storage_rejects_symlink(tmp_path: Path):
    path = tmp_path / "ollama"
    path.symlink_to(tmp_path)
    with pytest.raises(ValueError, match="link simbólico"):
        ollama_storage_creation_command(path, service_uid=0, service_gid=0)


def test_install_tree_rejects_nested_symlinks(tmp_path: Path):
    tree = tmp_path / "aurora"
    nested = tree / "assets" / "audio"
    nested.mkdir(parents=True)
    (nested / "outside-link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="link simbólico"):
        reject_symlinks_in_tree(tree)


def test_install_tree_can_ignore_preserved_python_venv_links(tmp_path: Path):
    tree = tmp_path / "aurora"
    (tree / ".venv").mkdir(parents=True)
    (tree / ".venv" / "python").symlink_to("/usr/bin/python3")
    reject_symlinks_in_tree(tree, ignored_directories={".venv"})


def test_release_recommendations_offer_latest_and_previous_prerelease_then_latest_stable():
    releases = [
        {"tag_name": "v1.5.7", "name": "Altair", "published_at": "2026-10-23T20:00:00Z", "draft": False, "prerelease": True},
        {"tag_name": "v1.5.6", "name": "Altair RC", "published_at": "2026-10-22T20:00:00Z", "draft": False, "prerelease": True},
        {"tag_name": "v1.4.0", "name": "Stable", "published_at": "2026-10-20T20:00:00Z", "draft": False, "prerelease": False},
        {"tag_name": "v9.0.0", "published_at": "2026-10-24T20:00:00Z", "draft": True, "prerelease": False},
    ]

    recommendations = recommend_releases(releases)

    assert [(item.channel, item.release["tag_name"]) for item in recommendations] == [
        ("latest_prerelease", "v1.5.7"),
        ("previous_prerelease", "v1.5.6"),
        ("latest_stable", "v1.4.0"),
    ]


def test_release_recommendations_return_only_available_channels_without_duplicates():
    releases = [
        {"tag_name": "v2.0.0", "published_at": "2026-10-24T12:00:00Z", "draft": False, "prerelease": False},
        {"tag_name": "bad-date", "published_at": "not-a-date", "draft": False, "prerelease": True},
    ]

    recommendations = recommend_releases(releases)

    assert [(item.channel, item.release["tag_name"]) for item in recommendations] == [
        ("latest_stable", "v2.0.0"),
    ]


def test_latest_launchpad_update_requires_newer_signed_metadata():
    asset = {
        "name": "aurora-launchpad-0.3.2-1.fc44.noarch.rpm",
        "browser_download_url": "https://github.com/Nylofofin/Aurora/releases/download/v1.8.0/aurora-launchpad-0.3.2-1.fc44.noarch.rpm",
        "digest": "sha256:" + "a" * 64,
        "size": 1234,
    }
    releases = [{
        "tag_name": "v1.8.0", "published_at": "2026-10-24T21:00:00Z",
        "draft": False, "prerelease": False, "assets": [asset],
    }]
    update = latest_launchpad_update(releases, "0.3.1")
    assert update["asset"] is asset
    assert latest_launchpad_update(releases, "0.3.2") is None


def test_latest_launchpad_update_finds_verified_rpm_in_prerelease():
    asset = {
        "name": "aurora-launchpad-0.4.9-1.fc44.noarch.rpm",
        "browser_download_url": "https://github.com/Nylofofin/Aurora/releases/download/v3.2.0-beta.1/aurora-launchpad-0.4.9-1.fc44.noarch.rpm",
        "digest": "sha256:" + "c" * 64,
        "size": 1234,
    }
    release = {
        "tag_name": "v3.2.0-beta.1", "published_at": "2026-10-26T01:40:23Z",
        "draft": False, "prerelease": True, "assets": [asset],
    }

    update = latest_launchpad_update([release], "0.4.8")

    assert update["asset"] is asset
    assert latest_launchpad_update([release], "0.4.9") is None


def test_latest_launchpad_update_rejects_untrusted_asset_metadata():
    bad = {
        "name": "aurora-launchpad-9.9.9-1.fc44.noarch.rpm",
        "browser_download_url": "https://evil.example/update.rpm",
        "digest": "sha256:" + "b" * 64,
        "size": 1234,
    }
    release = {"published_at": "2026-10-24T21:00:00Z", "draft": False, "prerelease": False, "assets": [bad]}
    assert latest_launchpad_update([release], "0.3.1") is None


def test_github_release_asset_redirect_hosts_are_strictly_allowlisted():
    assert is_official_github_download_url("https://github.com/Nylofofin/Aurora/releases/download/v1.8.0/update.rpm")
    assert is_official_github_download_url("https://release-assets.githubusercontent.com/github-production-release-asset/update.rpm")
    assert not is_official_github_download_url("http://release-assets.githubusercontent.com/update.rpm")
    assert not is_official_github_download_url("https://evil.example/update.rpm")


def test_newer_aurora_releases_returns_only_three_builds_above_installed():
    releases = [
        {"tag_name": "v1.8.0", "published_at": "2026-10-24T20:00:00Z", "draft": False, "prerelease": False},
        {"tag_name": "v1.7.4-beta.1", "published_at": "2026-10-24T19:00:00Z", "draft": False, "prerelease": True},
        {"tag_name": "v1.7.3", "published_at": "2026-10-24T18:00:00Z", "draft": False, "prerelease": False},
        {"tag_name": "v1.7.2", "published_at": "2026-10-24T17:00:00Z", "draft": False, "prerelease": False},
        {"tag_name": "v2.0.0-alpha.1", "published_at": "2026-10-24T16:00:00Z", "draft": False, "prerelease": True},
    ]
    found = newer_aurora_releases(releases, "1.7.2", 3)
    assert [item["tag_name"] for item in found] == ["v2.0.0-alpha.1", "v1.8.0", "v1.7.4-beta.1"]


def test_stable_update_candidates_skip_newer_prereleases():
    releases = [
        {"tag_name": "v2.2.0-beta.1", "published_at": "2026-10-25T20:00:00Z", "draft": False, "prerelease": True},
        {"tag_name": "v2.1.1", "published_at": "2026-10-25T19:00:00Z", "draft": False, "prerelease": False},
        {"tag_name": "v2.1.0", "published_at": "2026-10-25T18:00:00Z", "draft": False, "prerelease": False},
    ]
    found = newer_aurora_releases(releases, "2.1.0", 1, stable_only=True)
    assert [item["tag_name"] for item in found] == ["v2.1.1"]


def test_aurora_update_default_includes_newer_prerelease():
    releases = [
        {"tag_name": "v3.2.0-beta.1", "published_at": "2026-10-26T01:40:23Z", "draft": False, "prerelease": True},
        {"tag_name": "v3.1.1", "published_at": "2026-10-26T01:18:54Z", "draft": False, "prerelease": False},
    ]

    found = newer_aurora_releases(releases, "3.1.1", 1)

    assert [item["tag_name"] for item in found] == ["v3.2.0-beta.1"]


def test_launchpad_release_picker_names_stability_channel():
    from launchpad.aurora_launchpad_core import release_channel_label

    assert release_channel_label({"prerelease": True}) == "Pré-release · experimental"
    assert release_channel_label({"prerelease": False}) == "Release · estável"
    assert release_channel_label({}) == "Canal não informado"


def _make_tarball(path: Path, *, member_name="project/aurora.py", symlink=False):
    with tarfile.open(path, "w:gz") as bundle:
        info = tarfile.TarInfo(member_name)
        if symlink:
            info.type = tarfile.SYMTYPE
            info.linkname = "outside"
            bundle.addfile(info)
        else:
            content = b"aurora"
            info.size = len(content)
            bundle.addfile(info, io.BytesIO(content))


def test_release_tarball_extracts_only_project_files(tmp_path: Path):
    archive = tmp_path / "source.tar.gz"
    _make_tarball(archive)
    root = extract_release_tarball(archive, tmp_path / "extracted")
    assert root.name == "project"
    assert (root / "aurora.py").read_bytes() == b"aurora"


@pytest.mark.parametrize("member_name,symlink", [("../outside", False), ("project/link", True)])
def test_release_tarball_rejects_traversal_and_links(tmp_path: Path, member_name, symlink):
    archive = tmp_path / "source.tar.gz"
    _make_tarball(archive, member_name=member_name, symlink=symlink)
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError, match="inseguro|link"):
        extract_release_tarball(archive, destination)
    assert not destination.exists()
