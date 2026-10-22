#!/usr/bin/env python3
"""Compatibility entry point for the modular Aurora application."""
from __future__ import annotations
import aurora_fx
import aurora_integrations
from aurora_core.version import BUILD_ID, CODENAME, __version__

from aurora_core.config import (
    APP_CONFIG,
    APP_DIR,
    DEFAULTS,
    VOSK_PATH,
    hardware_profile,
    local_endpoint,
    settings_load,
    settings_save,
)
from aurora_core.memory import (
    MEMORY_FILE,
    MEMORY_LOCK,
    user_memory_load,
    user_memory_update,
)
from aurora_core.system.files import (
    create_user_file,
    normalize_words,
    resolve_natural_directory,
    xdg_user_directory,
)
from aurora_core.system.hardware import (
    system_hardware_summary,
)
from aurora_core.system.apps import (
    close_application,
    desktop_app_entries,
    find_desktop_app,
    launch_application,
    process_names_for_app,
)
from aurora_core.system.windows import (
    manage_window,
)
from aurora_core.system.volume import (
    control_volume,
    spoken_percentage,
)
from aurora_core.system.commands import (
    parse_local_command,
)
from aurora_core.web.parsers import (
    DuckDuckGoLiteResults,
    DuckDuckGoResults,
    PageMetadata,
    PageText,
    SearchResults,
)
from aurora_core.web.language import (
    ENGLISH_MARKERS,
    PORTUGUESE_MARKERS,
    likely_english,
    likely_portuguese,
)
from aurora_core.web.security import (
    PUBLIC_OPENER,
    PublicRedirectHandler,
    public_http_url,
)
from aurora_core.web.weather import (
    WMO_WEATHER,
    _get_json,
    weather_now,
)
from aurora_core.web.pipeline import (
    _SEARCH_CACHE,
    _SEARCH_CACHE_LOCK,
    _SEARCH_CACHE_TTL,
    _enrich_news_results,
    _fresh_query_terms,
    _google_news_pipeline_items,
    _has_expired_deadline,
    _has_stale_source_date,
    _has_stale_url_date,
    _independent_recent_source_count,
    _is_historical_query,
    _news_result_relevance,
    _parse_publication_date,
    _publication_within_window,
    _result_query_relevance,
    _search_page_excerpt,
    _search_public_web_uncached,
    _search_query_variants,
    _search_relevance,
    contextual_followup,
    contextual_source_request,
    current_search_window,
    current_web_query,
    factual_web_intent,
    guided_learning_intent,
    international_news_only,
    local_datetime_answer,
    news_search_intent,
    news_unconfirmed_message,
    read_public_page,
    requested_response_language,
    research_request_intent,
    search_failure_summary,
    search_google_news,
    search_intent,
    search_public_web,
    web_fetch,
)
from aurora_core.llm.prompts import (
    TOOLS,
    _ground_numeric_answer,
    _verified_fx_answer,
    assistant_system_prompt,
    complete_spoken_response,
    ground_search_answer,
    numeric_answer_intent,
    search_answer_prompts,
)
from aurora_core.llm.inference import (
    Inference,
)
from aurora_core.voice.wake import (
    LocalVoice,
)
from aurora_core.voice.tts import (
    Speaker,
)
from aurora_core.ui.orb import (
    AuroraOrb,
)
from aurora_core.service import (
    AuroraService,
    FXRequest,
    ModelWarmup,
    SearchRequest,
    WeatherRequest,
)
from aurora_core.main import (
    main,
)

if __name__ == "__main__":
    main()
