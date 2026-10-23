"""Privacy-minimal audit records for local actions."""

def classify_action_result(result: object) -> str:
    """Log whether an action completed, was merely dispatched, or failed.

    Never persist the returned text: it may contain a path, filename, or other
    user-provided value.
    """
    text = " ".join(str(result or "").casefold().split())
    if not text:
        return "returned"
    if any(phrase in text for phrase in (
        "não consegui", "não encontrei", "não criei", "não confirmei",
        "não foi possível", "ação falhou", "ação não disponível", "foi recusada",
    )):
        return "failed"
    if text.startswith(("solicitei", "enviei o comando", "enviei o sinal", "o sistema aceitou")):
        return "accepted"
    if text.startswith(("abri", "fechei", "criei", "volume", "som do pc", "janela",
                        "preferência salva", "esqueci")):
        return "completed"
    return "returned"


def audit_action(name: str, outcome: str = "returned", result: object = None) -> None:
    try:
        import aurora_integrations
        aurora_integrations._append_action_log(name, classify_action_result(result) if result is not None else outcome)
    except OSError:
        # A logging failure must not turn a completed local action into a false
        # failure message; the log writer already keeps the file user-private.
        pass
