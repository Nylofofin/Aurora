# SPDX-License-Identifier: GPL-3.0-only
from datetime import datetime
from types import SimpleNamespace

from aurora_core.system import routine


def test_greeting_uses_local_time_and_pc_username():
    assert routine.greeting_for(datetime(2026, 1, 1, 8), 'ana') == 'Bom dia, ana.'
    assert routine.greeting_for(datetime(2026, 1, 1, 15), 'ana') == 'Boa tarde, ana.'
    assert routine.greeting_for(datetime(2026, 1, 1, 22), 'ana') == 'Boa noite, ana.'


def test_voice_confirmation_accepts_only_clear_yes_or_no():
    assert routine.confirmation_intent('sim') is True
    assert routine.confirmation_intent('pode instalar') is True
    assert routine.confirmation_intent('não, deixa para depois') is False
    assert routine.confirmation_intent('pode reiniciar') is None
    assert routine.confirmation_intent('talvez') is None
    assert routine.confirmation_intent('') is None


def test_packagekit_parser_counts_updates_and_security_items():
    output = '''Refreshing software sources...
Results:
Security     kernel-core-6.18.2-200.fc44.x86_64 (updates)
Normal       firefox-145.0-1.fc44.x86_64 (updates)
Bugfix       glibc-2.43-2.fc44.x86_64 (updates)
'''
    parsed = routine.parse_packagekit_updates(output)
    assert parsed['packages'] == [
        'firefox-145.0-1.fc44.x86_64',
        'glibc-2.43-2.fc44.x86_64',
        'kernel-core-6.18.2-200.fc44.x86_64',
    ]
    assert parsed['security_count'] == 1


def test_packagekit_parser_ignores_non_result_text():
    assert routine.parse_packagekit_updates('Some package-1 (repo)\n') == {
        'packages': [], 'security_count': 0,
    }


def test_packagekit_query_is_cache_bounded_and_read_only(monkeypatch):
    monkeypatch.setattr(routine.shutil, 'which', lambda name: '/usr/bin/pkcon')
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout='Results:\nSecurity  pkg-1 (updates)\n')

    report = routine._packagekit_updates(fake_run)
    assert report['ok'] and report['security_count'] == 1
    assert calls[0][0] == ['/usr/bin/pkcon', '--plain', '--cache-age', '86400', 'get-updates']
    assert calls[0][1]['timeout'] == 35


def test_flatpak_probe_uses_cache_and_never_installs(monkeypatch):
    monkeypatch.setattr(routine.shutil, 'which', lambda name: '/usr/bin/flatpak')
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='org.example.Editor\n')

    report = routine._flatpak_updates('user', fake_run)
    assert report == {'ok': True, 'apps': ['org.example.Editor'], 'available': True}
    assert calls == [[
        '/usr/bin/flatpak', 'remote-ls', '--updates', '--columns=application',
        '--cached', '--user',
    ]]
    assert 'update' not in calls[0]


def test_firmware_probe_does_not_refresh_metadata(monkeypatch):
    monkeypatch.setattr(routine.shutil, 'which', lambda name: '/usr/bin/fwupdmgr')
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='No updatable devices\n')

    assert routine._firmware_updates(fake_run) == {
        'ok': True, 'devices': [], 'available': True,
    }
    assert calls == [['/usr/bin/fwupdmgr', 'get-updates', '--no-metadata-check']]


def test_logind_session_selection_and_lock_transitions():
    sessions = '''3 1000 nylofofin - 1192 manager - no -
2 1000 nylofofin seat0 1164 user tty2 no -
4 1001 another seat0 2210 user tty3 no -
'''
    assert routine.SessionUnlockMonitor._session_id(sessions, 1000) == '2'
    assert routine.SessionUnlockMonitor._session_id(sessions, 1002) == ''
    transition = routine.SessionUnlockMonitor._transition
    assert transition(True, False) == 'unlocked'
    assert transition(False, True) == 'locked'
    assert transition(False, False) is None
    assert transition(None, True) is None


def test_health_summary_only_reports_actionable_findings():
    report = {
        'rpm': {'ok': True, 'packages': ['pkg-1', 'pkg-2'], 'security_count': 1},
        'flatpak': {'ok': True, 'apps': ['org.example.App'], 'available': True},
        'firmware': {'ok': True, 'devices': ['1.2.3'], 'available': True},
        'warnings': ['pouco espaço livre em sistema: 4.0 GB (8%)'],
    }
    assert routine.summarize_health(report) == [
        '2 atualizações de pacotes do sistema, 1 de segurança',
        '1 aplicativo Flatpak com atualização disponível',
        '1 atualização de firmware; elas não serão instaladas automaticamente',
        'pouco espaço livre em sistema: 4.0 GB (8%)',
    ]


def test_proactive_health_summary_omits_failed_probes_as_pending_items():
    report = {
        'rpm': {'ok': False, 'packages': [], 'security_count': 0},
        'flatpak': {'ok': False, 'apps': [], 'available': True},
        'firmware': {'ok': False, 'devices': [], 'available': True},
        'warnings': ['não consegui concluir a verificação local', 'pouco espaço livre: 4 GB'],
    }
    assert routine.summarize_health(report, include_unavailable=False) == [
        'pouco espaço livre: 4 GB',
    ]


def test_update_worker_never_disables_package_signature_checks(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(routine.subprocess, 'run', fake_run)
    result = routine.SystemUpdateRequest._update(['/usr/bin/pkcon', 'update'])
    assert result.returncode == 0
    assert calls == [['/usr/bin/pkcon', 'update']]
    assert '--allow-untrusted' not in calls[0]
