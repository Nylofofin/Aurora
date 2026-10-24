"""Consistent confirmation policy for local desktop actions."""
# SPDX-License-Identifier: GPL-3.0-only


def requires_user_approval(name: str, args: dict | None = None,
                           explicit_user_request: bool = False) -> bool:
    """Require a second gesture only for risky or screen-mutating actions.

    A screenshot skips the extra Aurora prompt only when the user explicitly
    requested it. The desktop portal can still apply its own permission.
    """
    args = args if isinstance(args, dict) else {}
    return (
        name == "close_application"
        or name in {"agenda_clear"}
        or (name == "manage_window" and args.get("action") == "close")
        or (name == "obs_record" and (
            args.get("action") == "start" or not explicit_user_request))
        or (name in {"take_screenshot", "open_url"}
            and not explicit_user_request)
        or name in {"focus_accessible_window", "type_accessible_text"}
    )
