import aurora_core.web.weather as weather


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
