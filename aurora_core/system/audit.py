"""Privacy-minimal audit records for local actions."""


def audit_action(name: str, outcome: str = "returned") -> None:
    try:
        import aurora_integrations
        aurora_integrations._append_action_log(name, outcome)
    except OSError:
        # A logging failure must not turn a completed local action into a false
        # failure message; the log writer already keeps the file user-private.
        pass
