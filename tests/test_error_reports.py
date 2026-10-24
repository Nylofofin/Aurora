# SPDX-License-Identifier: GPL-3.0-only
from datetime import datetime
import os
from types import SimpleNamespace

from aurora_core.system.error_reports import (
    classify_error, schedule_user_service_restart, write_error_report,
)


def test_error_classifier_suggests_a_general_failure_category():
    assert classify_error('ConnectionRefusedError', 'localhost') == 'serviço local ou conexão recusada'
    assert classify_error('TimeoutError', 'timed out') == 'operação excedeu o tempo limite'
    assert classify_error('ModuleNotFoundError', 'No module named x') == 'dependência ausente ou incompatível'
    assert classify_error('RuntimeError', 'unexpected') == 'causa não identificada automaticamente'


def test_error_report_is_private_redacted_and_does_not_include_user_content(tmp_path):
    home = os.path.expanduser('~')
    report = write_error_report(
        tmp_path, context='falha na resposta', error_type='RuntimeError',
        message=f'falha em {home}/private/password=abc123 Authorization: Bearer abcdef1234567890',
        frames=[{'file': f'{home}/Projects/aurora/aurora_core/service.py',
                 'line': 42, 'function': 'ask'}],
        now=datetime(2026,10,23,12,30),
    )
    text = report.read_text()

    assert report.name == 'aurora-error-20261023-123000-000000.md'
    assert 'classificação automática' in text.casefold()
    assert 'abc123' not in text
    assert 'abcdef1234567890' not in text
    assert 'texto livre do erro foi omitido' in text
    assert home not in text
    assert 'prompt' not in text.casefold() or 'não contém prompts' in text.casefold()
    assert report.stat().st_mode & 0o777 == 0o600
    assert report.parent.stat().st_mode & 0o777 == 0o700


def test_error_report_never_overwrites_an_existing_report(tmp_path):
    now=datetime(2026,10,23,12,30)
    kwargs={'context':'teste','error_type':'RuntimeError','message':'falha','now':now}
    first=write_error_report(tmp_path,**kwargs)

    try:
        write_error_report(tmp_path,**kwargs)
    except FileExistsError:
        pass
    else:
        raise AssertionError('um relatório existente foi sobrescrito')
    assert first.exists()


def test_restart_is_scheduled_outside_the_aurora_service_process():
    calls=[]
    ok,reason=schedule_user_service_restart(
        which=lambda name: f'/usr/bin/{name}',
        runner=lambda argv,**kwargs: calls.append((argv,kwargs)) or SimpleNamespace(returncode=0,stdout='',stderr=''),
    )
    argv=calls[0][0]
    assert ok and reason=='reinício agendado'
    assert '--on-active=2s' in argv
    assert argv[-3:]==['--user','restart','aurora.service']


def test_restart_failure_is_reported_without_claiming_success():
    ok,reason=schedule_user_service_restart(
        which=lambda name: f'/usr/bin/{name}',
        runner=lambda *_args,**_kwargs: SimpleNamespace(returncode=1,stdout='',stderr='sem barramento'),
    )
    assert not ok
    assert reason=='sem barramento'
