"""Consistent confirmation policy for local desktop actions."""
# SPDX-License-Identifier: GPL-3.0-only


def requires_user_approval(name: str, args: dict | None = None,
                           explicit_user_request: bool = False) -> bool:
    """Require explicit confirmation before any action that changes local state."""
    args = args if isinstance(args, dict) else {}
    return (
        name in {
            "open_application", "close_application", "manage_window",
            "create_file", "remember_preference", "forget_preference",
            "agenda_add", "agenda_cancel", "agenda_clear", "take_screenshot",
            "obs_record", "open_url", "focus_accessible_window",
            "type_accessible_text", "timer_start", "timer_cancel",
            "timer_pause", "timer_resume",
        }
        or (name == "volume_control" and args.get("action", "status") != "status")
    )
