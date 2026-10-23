# SPDX-License-Identifier: GPL-3.0-only
import threading

import pytest
import aurora_core.web.weather as weather


def test_weather_json_uses_redirect_protected_public_opener(monkeypatch):
    validated = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return "https://api.open-meteo.com/v1/forecast"
        def read(self, _limit): return b'{"ok": true}'

    monkeypatch.setattr(weather, "public_http_url",
                        lambda url: validated.append(url) or url)
    monkeypatch.setattr(weather.PUBLIC_OPENER, "open",
                        lambda *_args, **_kwargs: Response())

    assert weather._get_json("https://api.open-meteo.com/v1/forecast") == {"ok": True}
    assert validated == [
        "https://api.open-meteo.com/v1/forecast",
        "https://api.open-meteo.com/v1/forecast",
    ]


def test_weather_total_timeout_includes_public_dns_validation(monkeypatch):
    release = threading.Event()

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return "https://api.open-meteo.com/v1/forecast"
        def read(self, _limit): return b'{}'

    def slow_validation(url):
        release.wait(0.5)
        return url

    monkeypatch.setattr(weather, "public_http_url", slow_validation)
    monkeypatch.setattr(weather.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: Response())
    with pytest.raises(TimeoutError, match="excedeu o tempo limite"):
        weather._get_json("https://api.open-meteo.com/v1/forecast", timeout=0.03)
    release.set()


def test_weather_place_ignores_forecast_day_as_a_city():
    assert weather._weather_place_from_prompt("previsão para amanhã") == ""
    assert weather._weather_place_from_prompt("clima para hoje") == ""


def test_weather_place_strips_forecast_day_after_city():
    assert weather._weather_place_from_prompt("tempo em São Paulo amanhã") == "São Paulo"
    assert weather._weather_place_from_prompt("previsão para São Paulo amanhã") == "São Paulo"


def test_explicit_city_after_forecast_day_takes_precedence():
    assert weather._weather_place_from_prompt("previsão para amanhã em Santos") == "Santos"
    assert weather._weather_place_from_prompt("previsão para o fim de semana em São Paulo") == "São Paulo"


def test_weather_place_supports_explicit_city_wording():
    assert weather._weather_place_from_prompt("clima na cidade de Recife") == "Recife"
