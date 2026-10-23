from aurora_core.system.audit import audit_action, classify_action_result


def test_action_result_log_distinguishes_completion_acceptance_and_failure():
    assert classify_action_result("Solicitei a abertura; o sistema aceitou.") == "accepted"
    assert classify_action_result("Volume ajustado para 40%.") == "completed"
    assert classify_action_result("Não consegui ajustar o volume.") == "failed"
    assert classify_action_result("O OBS aceitou o comando, mas não confirmei que a gravação está ativa.") == "failed"
    assert classify_action_result("A captura foi cancelada; nenhum arquivo foi salvo.") == "cancelled"
    assert classify_action_result("Autorização expirou; ação cancelada.") == "expired"


def test_action_audit_never_persists_the_returned_text(monkeypatch):
    import aurora_integrations

    rows = []
    monkeypatch.setattr(aurora_integrations, "_append_action_log",
                        lambda *args: rows.append(args))
    private_path = "/home/user/secret-document.txt"

    audit_action("open_application", result=f"Não encontrei o arquivo {private_path}.")

    assert rows == [("open_application", "failed")]
    assert private_path not in repr(rows)


def test_action_audit_records_elapsed_time_without_recording_result(monkeypatch):
    import aurora_integrations

    rows = []
    monkeypatch.setattr(aurora_integrations, "_append_action_log",
                        lambda *args: rows.append(args))

    audit_action("close_application", result="Fechei o aplicativo.", elapsed_ms=1234)

    assert rows == [("close_application", "completed", {"elapsed_ms": 1234})]
