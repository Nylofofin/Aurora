"""Compatibility facade for Aurora's desktop integrations."""
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
import urllib.parse

from aurora_core.system.action_log import _append_action_log
from aurora_core.system.obs import (
    OBS_REQUEST_TIMEOUT, OBS_STARTUP_TIMEOUT, _flatpak_obs_config_path,
    _flatpak_obs_settings, _obs_latest_log_is_safe_mode, _read_exact,
    _set_request_timeout, _ws_receive, _ws_send, obs_record,
)
from aurora_core.system.screenshot import (
    ScreenshotPortalError, _gnome_saved_screenshot_signature,
    _portal_request_object_path, _portal_response_code_type,
    _portal_response_slot, _recover_gnome_saved_screenshot, capture_screenshot,
    save_screenshot_uri, screenshot_parent_identifier, unique_screenshot_path,
)

def site_url_from_request(prompt: str) -> str | None:
    """Return a safe HTTP(S) URL only when speech clearly asks for a site."""
    text = " ".join(str(prompt or "").strip().split())
    text = re.sub(r"^\s*(?:(?:ei|olá)\s+)?aurora[\s,.:;!?-]*", "", text, flags=re.I)
    lowered = text.casefold()
    starters = ("abra o site ", "abra site ", "abre o site ", "abre site ",
                "abrir o site ", "abrir site ", "acesse o site ", "acesse site ",
                "abra o link ", "abre o link ", "abrir o link ",
                "abra o endereço ", "abre o endereço ", "abrir o endereço ")
    target = None
    for starter in starters:
        if lowered.startswith(starter):
            target = text[len(starter):].strip(" .,!?:;")
            break
    if target is None:
        # A spoken, fully qualified domain is unambiguous even without "site".
        command_prefixes = ("abra ", "abre ", "abrir ", "acesse ")
        for prefix in command_prefixes:
            if lowered.startswith(prefix):
                candidate = text[len(prefix):].strip(" .,!?:;")
                if "." in candidate and " " not in candidate:
                    target = candidate
                break
    if not target:
        return None
    if target.startswith(("http://", "https://")):
        candidate = target
    else:
        if "/" not in target and "." not in target:
            return None
        candidate = "https://" + target
    try:
        parsed = urllib.parse.urlsplit(candidate)
        parsed.port
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return None
    if any(c.isspace() for c in candidate):
        return None
    return candidate
