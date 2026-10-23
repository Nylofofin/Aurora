from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import gzip
import pytest
import re
import zlib

import aurora
import aurora_core.web.pipeline as search_pipeline
import aurora_core.web.security as web_security
import aurora_core.web.providers as search_providers
from aurora_core.web.intent import asks_latest_version
from aurora_core.web.http_body import decode_http_body

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


def test_stale_publication_is_rejected_and_recent_is_accepted():
    old = "Published February 4, 2025"
    recent = "Published October 20, 2026"
    assert aurora._has_stale_source_date(old, "7d", now=NOW)
    assert not aurora._has_stale_source_date(recent, "7d", now=NOW)
    stale_html = (FIXTURES / "stale-source.html").read_text()
    metadata = aurora.PageMetadata()
    metadata.feed(stale_html)
    assert metadata.dates[0][1].startswith("2025-")


def test_page_metadata_reads_json_ld_publication_dates():
    metadata = aurora.PageMetadata()
    metadata.feed('''<html><script type="application/ld+json">
      {"@context":"https://schema.org","@type":"NewsArticle",
       "datePublished":"2026-10-21T09:30:00-03:00",
       "dateModified":"2026-10-22T10:00:00-03:00"}
      </script></html>''')
    assert ("datepublished", "2026-10-21T09:30:00-03:00") in metadata.dates
    assert ("datemodified", "2026-10-22T10:00:00-03:00") in metadata.dates


def test_page_metadata_reads_relative_time_custom_elements():
    metadata = aurora.PageMetadata()
    metadata.feed('<relative-time datetime="2026-10-20T14:00:00Z">2 days ago</relative-time>')
    assert ("time", "2026-10-20T14:00:00Z") in metadata.dates


@pytest.mark.parametrize("encoding,raw", [
    ("gzip", gzip.compress(b"plain html text")),
    ("deflate", zlib.compress(b"plain html text")),
])
def test_http_response_body_decodes_supported_compression(encoding, raw):
    assert decode_http_body(raw, encoding, 100) == b"plain html text"


def test_http_response_body_rejects_compression_expansion_over_limit():
    with pytest.raises(ValueError, match="excede o limite"):
        decode_http_body(gzip.compress(b"A" * 10_000), "gzip", 100)


def test_search_page_excerpt_reads_compressed_html_and_publication_date(monkeypatch):
    import aurora_core.web.fetch as search_fetch
    from email.message import Message

    body = gzip.compress(b'''<html><head><meta property="article:published_time" content="2026-10-21T10:00:00Z"></head>
      <body><p>Nexa project version 3.15.1 was released after the latest test cycle. This release is available from the current project downloads page.</p></body></html>''')
    headers = Message()
    headers["Content-Type"] = "text/html; charset=utf-8"
    headers["Content-Encoding"] = "gzip"

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return "https://example.org/releases"
        def read(self, _limit): return body

    Response.headers = headers
    monkeypatch.setattr(search_fetch, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_fetch, "PUBLIC_OPENER", type("Opener", (), {"open": lambda *_args, **_kwargs: Response()})())

    excerpt, published = search_fetch._search_page_excerpt(
        "https://example.org/releases", "Nexa project version latest"
    )

    assert "3.15.1" in excerpt
    assert published == "21/10/2026"


def test_latest_version_intent_prioritizes_release_pages_over_current_news():
    query = "Qual é a última versão do OBS Studio?"
    release = {
        "provider": "Bing RSS", "host": "github.com", "url": "https://github.com/example/app/releases",
        "published": "", "score": 1.0,
    }
    news_tutorial = {
        "provider": "Bing Notícias", "host": "example.com", "url": "https://example.com/tutorial",
        "published": "22/10/2026", "score": 1.0,
    }

    assert asks_latest_version(query)
    assert not asks_latest_version("Quais são as notícias atuais do OBS Studio?")
    assert search_pipeline._candidate_rank(release, "30d", False, NOW.date(), 30, query) > search_pipeline._candidate_rank(
        news_tutorial, "30d", False, NOW.date(), 30, query
    )


def test_latest_version_requires_same_version_on_two_hosts():
    corroborating = [
        {"host": "project.example", "page_excerpt": "Current version 3.15.1"},
        {"host": "docs.example", "page_excerpt": "Documentation for version 3.15.1"},
    ]
    conflicting = [
        {"host": "project.example", "page_excerpt": "Current version 3.15.1"},
        {"host": "docs.example", "page_excerpt": "Documentation for version 3.14.9"},
    ]

    assert search_pipeline._version_source_consensus(corroborating)[0] == "3.15.1"
    assert search_pipeline._version_source_consensus(corroborating[:1]) is None
    assert search_pipeline._version_source_consensus(conflicting) is None


def test_latest_version_queries_generic_release_feed(monkeypatch):
    _force_provider_failure(monkeypatch)
    queries = []
    monkeypatch.setattr(search_pipeline, "search_bing_news", lambda query, *_args: queries.append(query) or [])

    search_pipeline._search_public_web_uncached("Qual é a última versão do Nexa Editor?", "30d", False)

    assert queries
    assert all("latest release" in query for query in queries)
    assert any("nexa" in query and "editor" in query for query in queries)


def test_modified_timestamp_does_not_override_known_old_publication_date(monkeypatch):
    import aurora_core.web.fetch as search_fetch
    from email.message import Message

    body = (FIXTURES / "edited-old-source.html").read_bytes()
    headers = Message()
    headers["Content-Type"] = "text/html; charset=utf-8"

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return "https://example.org/nexa-network-status"
        def read(self, _limit): return body

    monkeypatch.setattr(search_fetch, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_fetch.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: Response())
    Response.headers = headers
    excerpt, published = search_fetch._search_page_excerpt(
        "https://example.org/nexa-network-status", "Nexa network status"
    )

    assert "Nexa network status" in excerpt
    assert published == "12/03/2024"


def test_conflicting_current_claims_remain_relevant_as_separate_evidence():
    query = "Nexa network measured"
    claims = []
    for name in ("recent-source-a.html", "recent-source-b.html"):
        html = (FIXTURES / name).read_text()
        text = " ".join(re.findall(r">([^<>]+)<", html))
        claims.append(text)
    assert "18 units" in claims[0]
    assert "21 units" in claims[1]
    assert aurora._search_relevance(query, "Nexa network measurement update", claims[0]) > 0
    assert aurora._search_relevance(query, "Nexa network measurement update", claims[1]) > 0
    prompt, system = aurora.search_answer_prompts(
        "What did the Nexa network measure?", "Nexa network measured",
        ["Source A, 21/10/2026: " + claims[0], "Source B, 20/10/2026: " + claims[1]], now=NOW,
    )
    assert "18 units" in prompt and "21 units" in prompt
    assert "mencione a divergência" in prompt
    assert "divergências" in system


def test_current_fact_requires_two_independent_dated_publishers():
    one = [{"host": "source-a.example", "published": "21/10/2026"}]
    two = one + [{"host": "source-b.example", "published": "20/10/2026"}]
    stale = [{"host": "source-a.example", "published": "04/02/2025"}]
    assert aurora._independent_recent_source_count([], "7d", NOW) == 0
    assert aurora._independent_recent_source_count(one, "7d", NOW) == 1
    assert aurora._independent_recent_source_count(two, "7d", NOW) == 2
    duplicate_story = [
        {"host": "source-a.example", "published": "21/10/2026", "title": "Nexa network measurement update"},
        {"host": "source-b.example", "published": "20/10/2026", "title": "Nexa network measurement update"},
    ]
    assert aurora._independent_recent_source_count(duplicate_story, "7d", NOW) == 1
    assert aurora._independent_recent_source_count(stale, "7d", NOW) == 0


def test_publication_windows_use_elapsed_time_not_calendar_days():
    assert aurora._publication_within_window("2026-10-21T12:01:00Z", "1d", NOW)
    assert not aurora._publication_within_window("2026-10-21T11:59:00Z", "1d", NOW)
    assert aurora._publication_within_window("2026-10-15T12:01:00Z", "7d", NOW)
    assert not aurora._publication_within_window("2026-10-15T11:59:00Z", "7d", NOW)
    assert not aurora._publication_within_window("2026-10-22T12:01:00Z", "1d", NOW)


def test_localized_and_machine_feed_dates_are_parsed():
    for value in ("qua., 21 out. 2026 13:06:00 GMT", "Tue, 21 Oct 2026 13:06:00 GMT", "2026-10-21T13:06:00Z", "21/10/2026 13:06"):
        assert aurora._parse_publication_date(value).strftime("%d/%m/%Y") == "21/10/2026"


def test_accented_portuguese_news_question_compacts_without_function_words():
    from aurora_core.web.intent import _fresh_query_terms, _news_result_relevance, _search_query_variants

    query = "Quais são as notícias de hoje sobre tecnologia"
    variants = _search_query_variants(query, "1d")

    assert _fresh_query_terms(query) == {"tecnologia"}
    assert len(variants) == 2
    assert variants[1][0] == "noticias tecnologia 2026"
    assert _news_result_relevance(query, "Tecnologia: nova medida anunciada hoje") == 1.0
    assert _news_result_relevance(query, "Instituto Federal suspende aulas após ameaça") == 0.0


def test_google_news_rss_hour_survives_pipeline_freshness_filter(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import aurora_core.web.freshness as freshness

    fixed_now = datetime(2026, 10, 22, 15, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
    monkeypatch.setattr(search_providers, "public_http_url", lambda url: url)
    monkeypatch.setattr(
        search_providers,
        "_publication_within_window",
        lambda value, window: freshness._publication_within_window(value, window, now=fixed_now),
    )
    rss = "Google Notícias:\nNexa network measurement update [Jornal · 21/10/2026 16:00] :: Nexa network measurement data — https://news.google.com/articles/story"

    items = search_providers._google_news_pipeline_items(
        rss, "Nexa network measurement", "1d"
    )

    assert len(items) == 1
    assert items[0]["published"] == "21/10/2026 16:00"


def test_google_news_provider_uses_the_public_redirect_protected_opener(monkeypatch):
    from email.message import Message

    calls = []
    class Response:
        headers = Message()
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return "https://news.google.com/rss/search?q=example"
        def read(self, _limit): return b"<rss><channel /></rss>"

    class Opener:
        def open(self, request, timeout):
            calls.append((request.full_url, timeout))
            return Response()

    monkeypatch.setattr(search_providers, "PUBLIC_OPENER", Opener())
    monkeypatch.setattr(search_providers, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_providers.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unprotected urlopen used")))

    result = search_providers.search_google_news("example", "7d")

    assert calls and calls[0][0].startswith("https://news.google.com/rss/search?")
    assert calls[0][1] == 3.5
    assert "Não encontrei publicações recentes" in result


def test_bing_news_rss_unwraps_publisher_links_and_keeps_feed_dates(monkeypatch):
    from email.message import Message
    from urllib.parse import quote

    target = "https://publisher.example/tecnologia/noticia"
    rss = f"""<rss><channel><item>
      <title>Tecnologia recebe novo recurso hoje</title>
      <description>Atualização sobre tecnologia.</description>
      <link>https://www.bing.com/news/apiclick.aspx?url={quote(target, safe='')}</link>
      <pubDate>Wed, 21 Oct 2026 15:00:00 GMT</pubDate><source>Jornal Exemplo</source>
    </item></channel></rss>""".encode()

    class Response:
        headers = Message()
        def __init__(self): self.headers["Content-Type"] = "application/xml; charset=utf-8"
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def getcode(self): return 200
        def geturl(self): return "https://www.bing.com/news/search?format=rss"
        def read(self, _limit): return rss

    monkeypatch.setattr(search_providers.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(search_providers, "public_http_url", lambda url: url)

    rows = search_providers.search_bing_news("notícias de tecnologia hoje")

    assert rows == [(target, "Tecnologia recebe novo recurso hoje", "Atualização sobre tecnologia.", "21/10/2026 12:00", "Jornal Exemplo")]


def test_bing_news_rejects_unsafe_unwrapped_publisher_url(monkeypatch):
    from email.message import Message
    from urllib.parse import quote

    target = "http://127.0.0.1/private"
    rss = f"<rss><channel><item><title>Tecnologia</title><link>https://www.bing.com/news/apiclick.aspx?url={quote(target, safe='')}</link><pubDate>Wed, 21 Oct 2026 15:00:00 GMT</pubDate></item></channel></rss>".encode()

    class Response:
        headers = Message()
        def __init__(self): self.headers["Content-Type"] = "application/rss+xml"
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def getcode(self): return 200
        def geturl(self): return "https://www.bing.com/news/search?format=rss"
        def read(self, _limit): return rss

    monkeypatch.setattr(search_providers.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: Response())
    def validate(url):
        if url.startswith("http://127."):
            raise ValueError("private address")
        return url
    monkeypatch.setattr(search_providers, "public_http_url", validate)

    assert search_providers.search_bing_news("notícias de tecnologia hoje") == []


def test_bing_news_candidates_use_common_pipeline_and_feed_date_when_page_has_no_date(monkeypatch):
    today = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
    recent_yesterday = today
    feed_date = datetime.now().astimezone().strftime("%d/%m/%Y")
    news_queries = []
    google_feed = "Google Notícias:\n"
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: google_feed)
    def bing_news(query, *_args):
        news_queries.append(query)
        if query.endswith(" Brasil"):
            return []
        return [
            ("https://publisher-a.example/tecnologia", "Tecnologia recebe novo recurso", "Atualização sobre tecnologia.", today, ""),
            ("https://publisher-b.example/tecnologia", "Tecnologia anuncia outra novidade", "Informações de tecnologia.", recent_yesterday, ""),
        ]
    monkeypatch.setattr(search_pipeline, "search_bing_news", bing_news)
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_pipeline.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("search unavailable")))
    reads = []
    def read(url, _query, timeout=2.5):
        reads.append(url)
        if "news.google.com" in url:
            raise OSError("Google wrapper does not expose a publisher article")
        return ("Tecnologia: reportagem com detalhes confirmados nesta página.", "")
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)

    output = search_pipeline._search_public_web_uncached("quais as notícias de tecnologia hoje", "1d", True)

    assert len(reads) == 2
    assert set(reads) == {
        "https://publisher-a.example/tecnologia",
        "https://publisher-b.example/tecnologia",
    }
    assert news_queries == ["tecnologia", "tecnologia Brasil"]
    assert "Feed RSS: publisher-a.example" in output
    assert "Feed RSS: publisher-b.example" in output
    assert "Bing Notícias" in output
    assert "Trecho da página aberta agora" in output


def test_current_news_retries_reserve_pages_after_blocked_candidates(monkeypatch):
    import threading
    import time

    now = datetime.now().astimezone()
    today = now.strftime("%d/%m/%Y")
    stories = [
        ("https://publisher-a.example/ai", "Tecnologia recebe atualização importante", "Notícia de tecnologia com detalhes.", now.strftime("%d/%m/%Y %H:%M"), ""),
        ("https://publisher-b.example/ai", "Tecnologia anuncia nova medida", "Notícia de tecnologia com informações.", now.strftime("%d/%m/%Y %H:%M"), ""),
        ("https://publisher-c.example/ai", "Tecnologia ganha novo serviço", "Notícia de tecnologia com anúncio.", now.strftime("%d/%m/%Y %H:%M"), ""),
        ("https://publisher-d.example/ai", "Tecnologia apresenta nova iniciativa", "Notícia de tecnologia com contexto.", now.strftime("%d/%m/%Y %H:%M"), ""),
    ]
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: "Google Notícias:\n")
    monkeypatch.setattr(search_pipeline, "search_bing_news", lambda query, *_args: [] if query.endswith(" Brasil") else stories)
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_pipeline.PUBLIC_OPENER, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("search unavailable")))
    lock = threading.Lock()
    state = {"active": 0, "max_active": 0}
    reads = []

    def read(url, _query, timeout=2.5):
        with lock:
            reads.append(url)
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            time.sleep(0.03)
            if "publisher-b" in url:
                raise OSError("publisher blocked the request")
            return ("Tecnologia: reportagem com informação confirmada nesta página.", today)
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = search_pipeline._search_public_web_uncached("quais as notícias de tecnologia hoje", "1d", True)

    assert len(reads) == 4
    assert state["max_active"] <= 2
    assert "As fontes encontradas não bastam" not in output
    assert "publisher-a.example" in output and "publisher-c.example" in output


def test_current_bing_search_rss_date_is_not_treated_as_publisher_date(monkeypatch):
    from email.utils import format_datetime

    pub_date = format_datetime(datetime.now().astimezone())
    rss = f"""<rss><channel>
      <item><title>Nexa network measurement update</title><description>Nexa network measurement report confirms an update.</description><link>https://source-a.example/story</link><pubDate>{pub_date}</pubDate></item>
      <item><title>Nexa network measurement report</title><description>Independent Nexa network measurement report confirms another update.</description><link>https://source-b.example/story</link><pubDate>{pub_date}</pubDate></item>
    </channel></rss>""".encode()

    class Response:
        def __init__(self, url, body): self.url=url; self.body=body
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return self.url
        def read(self, _limit): return self.body

    class Opener:
        def open(self, request, timeout):
            url=request.full_url
            return Response(url, rss if "bing.com/search" in url else b"<html></html>")

    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: "Google Notícias:\\n")
    monkeypatch.setattr(search_pipeline, "search_bing_news", lambda *_args: [])
    monkeypatch.setattr(search_pipeline, "PUBLIC_OPENER", Opener())
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    reads=[]

    def read_page(url, _query, timeout=2.5):
        reads.append(url)
        return ("Nexa network measurement findings confirmed by this page.", "")

    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read_page)
    output=search_pipeline._search_public_web_uncached("Nexa network measurement today", "7d", True)

    assert len(reads) == 2
    assert "Resultados combinados" not in output
    assert "Não consegui ler páginas com conteúdo verificável" in output


def test_current_fact_uses_bing_news_feed_when_general_search_has_no_verified_sources(monkeypatch):
    today=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
    stories=[
        ("https://education-a.example/minister", "Ministro da Educação anuncia medida", "O atual ministro da Educação detalhou uma medida nesta semana.", today, "Educação Hoje"),
        ("https://education-b.example/minister", "Ministro da Educação participa de evento", "O atual ministro da Educação participou de um evento nesta semana.", today, "Jornal Educação"),
    ]

    class Response:
        def __init__(self,url,body): self.url=url; self.body=body
        def __enter__(self): return self
        def __exit__(self,*_args): return None
        def geturl(self): return self.url
        def read(self,_limit): return self.body

    class Opener:
        def open(self,request,timeout):
            url=request.full_url
            return Response(url,b"<rss><channel/></rss>" if "bing.com/search" in url else b"<html></html>")

    monkeypatch.setattr(search_pipeline,"search_google_news",lambda *_args:"Google Notícias:\\n")
    monkeypatch.setattr(search_pipeline,"search_bing_news",lambda *_args:stories)
    monkeypatch.setattr(search_pipeline,"PUBLIC_OPENER",Opener())
    monkeypatch.setattr(search_pipeline,"public_http_url",lambda url:url)
    page_reads=[]

    def read_page(url,_query,timeout=2.5):
        page_reads.append(url)
        return ("O atual ministro da Educação participou e explicou a medida anunciada.","")

    monkeypatch.setattr(search_pipeline,"_search_page_excerpt",read_page)
    output=search_pipeline._search_public_web_uncached("Quem é o ministro da Educação?","30d",False)

    assert len(page_reads)==2
    assert "Feed RSS: Educação Hoje" in output
    assert "Feed RSS: Jornal Educação" in output
    assert "Não consegui" not in output


def test_public_redirect_handler_rejects_loopback_destinations():
    from urllib.request import Request

    handler = web_security.PublicRedirectHandler()
    request = Request("https://news.google.com/rss")
    with pytest.raises(ValueError, match="públicos|local|reservado"):
        handler.redirect_request(request, None, 302, "Found", {}, "http://127.0.0.1/")


def test_public_url_dns_validation_has_a_bounded_timeout(monkeypatch):
    import threading

    release = threading.Event()
    monkeypatch.setattr(web_security, "DNS_VALIDATION_TIMEOUT", 0.02)

    def slow_dns(*_args, **_kwargs):
        release.wait(0.5)
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(web_security.socket, "getaddrinfo", slow_dns)
    with pytest.raises(TimeoutError, match="validação DNS"):
        web_security.public_http_url("https://example.test/article")
    release.set()


def test_public_http_connection_uses_the_validated_ip_even_if_dns_changes(monkeypatch):
    public = [(2, 1, 6, "", ("93.184.216.34", 0))]
    private = [(2, 1, 6, "", ("127.0.0.1", 0))]
    lookups = []
    monkeypatch.setattr(web_security, "_resolve_public_host", lambda host: (lookups.append(host) or public))
    web_security.public_http_url("http://rebind.example:443/article")
    handler = web_security.PublicHTTPHandler()
    request = urllib.request.Request("http://rebind.example:443/article")
    def capture_connection(factory, req, **kwargs):
        return factory(req.host, timeout=1, **kwargs)
    monkeypatch.setattr(handler, "do_open", capture_connection)
    connection = handler.http_open(request)
    assert connection._public_addresses == ("93.184.216.34",)
    assert lookups == ["rebind.example"]

    connections = []
    class ConnectedSocket:
        def setsockopt(self, *_args): pass
    monkeypatch.setattr(web_security, "_resolve_public_host", lambda _host: private)
    monkeypatch.setattr(web_security.socket, "create_connection", lambda address, *args, **kwargs: (
        connections.append(address) or ConnectedSocket()
    ))
    connection.connect()

    assert connections == [("93.184.216.34", 443)]


def test_pinned_https_keeps_original_hostname_for_tls_sni(monkeypatch):
    connections = []
    class ConnectedSocket:
        def setsockopt(self, *_args): pass
    class TLSContext:
        def wrap_socket(self, sock, server_hostname):
            self.server_hostname = server_hostname
            return sock
    context = TLSContext()
    monkeypatch.setattr(web_security.socket, "create_connection", lambda address, *args, **kwargs: (
        connections.append(address) or ConnectedSocket()
    ))
    connection = web_security._PinnedHTTPSConnection(
        "example.test", ("93.184.216.34",), context=context, timeout=1
    )
    connection.connect()

    assert connections == [("93.184.216.34", 443)]
    assert context.server_hostname == "example.test"


def test_public_url_rejects_a_domain_with_any_private_dns_answer(monkeypatch):
    answers = [
        (2, 1, 6, "", ("93.184.216.34", 0)),
        (2, 1, 6, "", ("10.0.0.8", 0)),
    ]
    monkeypatch.setattr(web_security, "_resolve_public_host", lambda _host: answers)
    with pytest.raises(ValueError, match="rede local"):
        web_security.public_http_url("https://mixed.example/page")


def test_public_dns_cache_is_short_lived_and_bounded_by_configured_ttl(monkeypatch):
    import time

    calls = []
    answer = [(2, 1, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(web_security, "DNS_CACHE_TTL", 0.01)
    monkeypatch.setattr(web_security, "_resolve_public_host", lambda host: (calls.append(host) or answer))
    assert web_security._public_addresses("short-cache.example") == ("93.184.216.34",)
    assert web_security._public_addresses("short-cache.example") == ("93.184.216.34",)
    assert len(calls) == 1

    time.sleep(0.02)
    assert web_security._public_addresses("short-cache.example") == ("93.184.216.34",)
    assert len(calls) == 2


def test_question_intent_and_time_window_are_topic_independent():
    assert aurora.factual_web_intent("Qual é a concentração atual da amostra?")
    assert aurora.current_search_window("Qual é a concentração atual da amostra?") == "30d"
    assert not aurora.factual_web_intent("Abra a calculadora")
    assert aurora.current_search_window("Qual era a concentração em 2024?") == ""
    assert aurora.current_web_query("Nexa network current measurement", "30d").endswith(str(NOW.year))


def test_present_tense_identity_questions_require_recent_evidence_without_topic_lists():
    assert aurora.current_search_window("Quem é o ministro da Educação?") == "30d"
    assert aurora.current_search_window("Who is the director of the agency?") == "30d"
    assert aurora.current_search_window("Quem foi o presidente do Brasil em 1980?") == ""
    assert aurora.current_search_window("Quem é você?") == ""
    assert aurora.current_search_window("Quem é Albert Einstein?") == ""


def test_current_factual_answer_has_deterministic_source_and_date_attribution():
    from aurora_core.llm.prompts import ensure_current_source_attribution

    sources=["g1.globo.com (22/10/2026)","jr.jor.br (22/10/2026)"]
    answer=ensure_current_source_attribution("Quem é o ministro da Educação?","Leonardo Barchini ocupa o cargo.",sources)
    assert "Fontes consultadas: g1.globo.com (22/10/2026) e jr.jor.br (22/10/2026)." in answer

    already_cited=ensure_current_source_attribution(
        "Quem é o ministro da Educação?",
        "Leonardo Barchini. Fonte: g1.globo.com (22/10/2026). jr.jor.br (22/10/2026)",
        sources,
    )
    assert already_cited.count("g1.globo.com") == 1
    assert already_cited.count("jr.jor.br") == 1
    assert ensure_current_source_attribution("O que é fotossíntese?","Processo biológico.",sources)=="Processo biológico."


def test_recent_plural_phrasing_triggers_current_search_and_compacts_request_words():
    from aurora_core.web.intent import _search_query_variants

    query = "O que é o Geyser para Minecraft e quais as novidades mais recentes?"
    variants = _search_query_variants(query, "30d")

    assert aurora.current_search_window(query) == "30d"
    assert aurora._fresh_query_terms(query) == {"geyser", "minecraft"}
    assert variants[1][0] == f"Geyser Minecraft {NOW.year}"
    assert aurora._search_relevance(query, "Geyser | GeyserMC", "Minecraft Java and Bedrock cross-play") > 0


def test_news_format_terms_are_removed_only_when_a_subject_remains():
    query = "quais as notícias de tecnologia hoje"
    assert aurora._fresh_query_terms(query) == {"tecnologia"}
    assert aurora._search_relevance(query, "Novidades sobre tecnologia e ciência", "") > 0
    assert aurora._search_relevance(query, "Resultado sobre política e futebol", "") == 0.0
    assert aurora._fresh_query_terms("notícias de hoje") == {"noticias"}
    assert aurora._search_relevance("notícias de hoje", "Notícias do dia", "") == 1.0
    assert aurora._search_relevance("notícias de hoje sobre esportes", "Esporte brasileiro ganha destaque", "") > 0
    assert aurora._search_relevance("notícias de hoje sobre tecnologias", "Notícias sobre tecnologia", "") > 0


def test_current_dollar_question_does_not_require_question_words_for_relevance():
    query = "Quanto está o dólar agora"
    assert aurora._fresh_query_terms(query) == {"dolar"}
    assert aurora._search_relevance(query, "Dólar hoje fica estável", "Cotação da moeda americana") == 1.0
    assert aurora._search_relevance(query, "Quanto - Dicio", "Significado da palavra quanto") == 0.0


def test_numeric_answers_must_use_numbers_literal_in_evidence():
    evidence = ["Dólar fica estável hoje; petróleo a US$ 112."]
    assert aurora._ground_numeric_answer(
        "O dólar está em torno de 52,50 reais.", evidence,
        ["Folha de S.Paulo (22/10/2026)", "Estadão (22/10/2026)"],
    ) == "Não consegui confirmar os valores numéricos com os trechos consultados. Fontes: Folha de S.Paulo (22/10/2026), Estadão (22/10/2026)."
    assert aurora._ground_numeric_answer("O petróleo está a US$ 112.", evidence, []) == "O petróleo está a US$ 112."
    prompt, system = aurora.search_answer_prompts("Qual o valor?", "valor atual", evidence, now=NOW)
    assert "mesma sequência numérica aparecer literalmente" in prompt
    assert "Só informe um valor numérico se a mesma sequência numérica aparecer literalmente" in system


def test_news_dates_and_headline_numbers_do_not_trigger_numeric_guard():
    answer = "Tecnopuc Experience 2026 reúne empresas de saúde e tecnologia, segundo o Jornal do Comércio em 22/10/2026."
    evidence = ["Título: Tecnopuc Experience 2026 reúne empresas de saúde e tecnologia | Data: 22/10/2026"]
    assert not aurora.numeric_answer_intent("quais as notícias de tecnologia hoje")
    assert aurora.ground_search_answer("quais as notícias de tecnologia hoje", answer, evidence, ["Jornal do Comércio"]) == answer
    assert aurora.ground_search_answer("notícias de hoje", "Custa 52,50 reais.", evidence, ["fonte"]) == "Custa 52,50 reais."


def test_news_summary_prompt_preserves_claim_and_publisher_attribution():
    prompt, system = aurora.search_answer_prompts(
        "Quais as notícias de tecnologia hoje?", "tecnologia",
        ["Título: Acordo é firmado, segundo o Departamento de Estado | Fonte: valor.globo.com"],
    )
    assert "não transforme “segundo X” em “X anunciou/publicou”" in prompt
    assert "nomeie o veículo identificado nos trechos" in system


def test_numeric_guard_failure_message_matches_news_intent():
    result = aurora.ground_search_answer(
        "quantas notícias recentes sobre tecnologia?", "Foram 12 notícias.",
        ["A fonte menciona tecnologia."], ["Jornal"],
    )
    assert result.startswith("Não consegui confirmar notícias recentes sobre isso.")
    assert "valor" not in result.lower()


def test_incomplete_stream_tail_is_not_spoken():
    full = "As notícias incluem duas atualizações completas. A terceira começa em 21"
    assert aurora.complete_spoken_response(full) == "As notícias incluem duas atualizações completas."
    assert aurora.complete_spoken_response("A notícia termina corretamente.") == "A notícia termina corretamente."
    assert aurora.complete_spoken_response("fragmento sem pontuação") == ""


def test_news_results_must_match_subject_or_be_a_general_roundup():
    assert aurora._news_result_relevance(
        "quais as notícias de tecnologia hoje", "Novidades sobre tecnologia", ""
    ) > 0
    assert aurora._news_result_relevance(
        "quais as notícias de tecnologia hoje", "Notícias sobre edital", "concursos"
    ) == 0.0
    assert aurora._news_result_relevance(
        "notícias de hoje", "Principais notícias do mundo na manhã de hoje", ""
    ) > 0
    assert aurora._news_result_relevance(
        "notícias de hoje", "Notícias sobre edital de 22 de outubro", ""
    ) == 0.0
    assert aurora.news_unconfirmed_message().startswith("Não consegui confirmar notícias")


def test_news_prompt_never_turns_headline_into_price_request():
    prompt, system = aurora.search_answer_prompts(
        "notícias de hoje", "notícias de hoje", ["Notícias sobre edital; data 22/10/2026"]
    )
    assert "números e datas de manchetes são metadados" in prompt
    assert "Não consegui confirmar o valor" not in prompt + system
    assert "manchete isolada em resposta sobre preço" in system


def test_numeric_guard_decimal_currency_percent_and_spelled_number_edges():
    fallback = "Não consegui confirmar os valores numéricos com os trechos consultados. Fontes: fonte."
    assert aurora._ground_numeric_answer("O valor é 5.40.", ["O valor é 5,40."], ["fonte"]) == "O valor é 5.40."
    assert aurora._ground_numeric_answer("O valor é 5,041.", ["O valor é 5.041."], ["fonte"]) == "O valor é 5,041."
    assert aurora._ground_numeric_answer("Custa R$ 5,40.", ["O valor é 5.40."], ["fonte"]) == "Custa R$ 5,40."
    assert aurora._ground_numeric_answer("A taxa é 0.5%.", ["A taxa é 0,5%."], ["fonte"]) == "A taxa é 0.5%."
    assert aurora._ground_numeric_answer("A taxa é 0,5%.", ["A taxa é 0,5."], ["fonte"]) == fallback
    assert aurora._ground_numeric_answer("A taxa é 0,5.", ["A taxa é 0,5%."], ["fonte"]) == fallback
    assert aurora._ground_numeric_answer("Custa cinquenta e dois reais.", ["O dólar está estável."], ["fonte"]) == fallback
    assert aurora._ground_numeric_answer("Custa cinquenta e dois reais.", ["O preço é cinquenta e dois reais."], ["fonte"]) == "Custa cinquenta e dois reais."
    assert aurora._ground_numeric_answer("É um ponto importante.", ["É uma observação relevante."], ["fonte"]) == "É um ponto importante."


def test_structured_fx_answer_must_say_api_values_and_accept_equivalent_decimal_format():
    from datetime import date
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "AwesomeAPI", "USD", "BRL", Decimal("5.045"), date(2026, 10, 22),
        "12:30:00 UTC-3", Decimal("5.04"), Decimal("5.05"),
    )
    safe = aurora._verified_fx_answer("O dólar está em 5.03 e 5.05.", quote)
    assert safe.startswith("Não confirmei o valor numérico.")
    incomplete = "O dólar está em 5,04 para compra e R$ 5,05 para venda."
    assert aurora._verified_fx_answer(incomplete, quote) == incomplete
    spoken = "Compra R$ 5,04 e venda R$ 5,05, conforme a cotação."
    assert aurora._verified_fx_answer(spoken, quote) == spoken


def test_large_fx_values_use_thousands_separator_and_guard_accepts_both_forms():
    from datetime import date
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "AwesomeAPI", "BTC", "BRL", Decimal("411528"), date(2026, 10, 22),
        "12:30:00 UTC-3", Decimal("411528"), Decimal("411529"),
    )
    formatted = aurora.aurora_fx.format_quote(quote)
    assert "411.528 de compra" in formatted
    assert "411.529 de venda" in formatted
    assert aurora._verified_fx_answer(formatted, quote) == formatted
    ungrouped = "Bitcoin compra 411528 reais e venda 411529 reais."
    assert aurora._verified_fx_answer(ungrouped, quote) == ungrouped


def test_structured_conversion_requires_both_rate_and_converted_value():
    from datetime import date, datetime
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "Frankfurter", "USD", "BRL", Decimal("5.6528"), date(2026, 10, 22),
        amount=Decimal("100"), converted=Decimal("565.28"),
        retrieved_at=datetime(2026, 10, 22, 12, 50, 31, tzinfo=aurora.aurora_fx.LOCAL_TZ),
    )
    answer = aurora.aurora_fx.format_quote(quote)
    assert aurora._verified_fx_answer(answer, quote) == answer
    assert aurora._verified_fx_answer("100 USD equivalem a R$ 565,28.", quote).startswith("Não confirmei o valor numérico.")


def test_old_awesome_quote_warning_preserves_numeric_verification():
    from datetime import date
    from decimal import Decimal
    quote = aurora.aurora_fx.FXQuote(
        "AwesomeAPI", "USD", "BRL", Decimal("5.045"), date(2026, 10, 22),
        "12:00:00 UTC-3", Decimal("5.04"), Decimal("5.05"), stale=True,
    )
    answer = aurora.aurora_fx.format_quote(quote)
    assert "não a apresento como valor de agora" in answer
    assert aurora._verified_fx_answer(answer, quote) == answer


def _google_news_test_rows(count=3):
    from datetime import date
    published = date.today().strftime("%d/%m/%Y")
    return "Google Notícias:\n" + "\n".join(
        f"Nexa network measurement update {index} [Publisher {index} · {published}] :: Nexa network measurement reported today — https://news.google.com/articles/story-{index}"
        for index in range(1, count + 1)
    )


def _force_provider_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("provider unavailable")
    monkeypatch.setattr(web_security.PUBLIC_OPENER, "open", fail)
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda query, window: _google_news_test_rows())


def test_news_query_falls_back_to_ddg_and_bing_when_google_news_fails(monkeypatch):
    from datetime import datetime, timezone
    from email.utils import format_datetime

    monkeypatch.setattr(search_pipeline, "search_google_news",
                        lambda *_args: (_ for _ in ()).throw(TimeoutError("Google News timed out")))
    pub_date = format_datetime(datetime.now(timezone.utc))
    rss = """<rss><channel>
      <item><title>Nexa network measurement update</title><description>Nexa network measurement report confirmed.</description><link>https://source-a.example/story</link><pubDate>DATE</pubDate></item>
      <item><title>Nexa network measurement report</title><description>Independent Nexa network measurement report confirmed.</description><link>https://source-b.example/story</link><pubDate>DATE</pubDate></item>
    </channel></rss>""".replace("DATE", pub_date).encode()
    calls = []

    class Response:
        def __init__(self, url, body): self.url=url; self.body=body
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def geturl(self): return self.url
        def read(self, _limit): return self.body

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            if "duckduckgo.com" in request.full_url:
                return Response(request.full_url, b"<html></html>")
            return Response(request.full_url, rss)

    monkeypatch.setattr(search_pipeline, "PUBLIC_OPENER", Opener())
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    reads = []
    def read_page(url, _query, timeout=2.5):
        reads.append(url)
        return ("Nexa network measurement findings confirmed by the report.", today)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read_page)

    output = search_pipeline._search_public_web_uncached(
        "Nexa network measurement news today", "7d", True
    )

    assert any("duckduckgo.com/lite/" in url for url in calls)
    assert any("bing.com/search" in url for url in calls)
    assert len(reads) == 2
    assert "Google Notícias: TimeoutError" not in output
    assert "Bing RSS" in output


def test_google_news_wrapper_candidates_do_not_skip_compact_provider_query(monkeypatch):
    requested_urls = []
    rss = _google_news_test_rows().replace("Nexa network measurement", "technology")
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: rss)
    monkeypatch.setattr(search_pipeline, "_search_query_variants", lambda *_args: [
        ("Quais são as notícias de hoje sobre tecnologia 2026", "Quais são as notícias de hoje sobre tecnologia"),
        ("noticias tecnologia 2026", "noticias tecnologia"),
    ])
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)

    class Opener:
        def open(self, request, timeout):
            requested_urls.append(request.full_url)
            raise OSError("provider unavailable")

    monkeypatch.setattr(search_pipeline.PUBLIC_OPENER, "open", Opener().open)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", lambda *_args: "")

    search_pipeline._search_public_web_uncached(
        "Quais são as notícias de hoje sobre tecnologia", "1d", True
    )

    assert any("q=noticias+tecnologia+2026" in url for url in requested_urls)


def test_google_news_fallback_uses_common_page_pipeline_and_caps_reads_at_two(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []
    published = datetime.now().astimezone().strftime("%d/%m/%Y")
    def read(url, query, timeout=2.5):
        calls.append((url, timeout))
        return ("Nexa network measurement reported today in the page.", published)
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached("Nexa network measurement today", "7d", False)
    assert len(calls) == 2
    assert "Google Notícias" in output
    assert "Trecho da página aberta agora" in output
    assert "Nexa network measurement" in output


def test_current_search_skips_duplicate_publisher_to_read_an_independent_source(monkeypatch):
    _force_provider_failure(monkeypatch)
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    rss = "Google Notícias:\n" + "\n".join((
        f"Nexa network measurement results [Daily News · {today}] :: Nexa network measurement reported today — https://news.google.com/articles/story-1",
        f"Nexa network measurement details [Daily News · {today}] :: Nexa network measurement reported today — https://news.google.com/articles/story-2",
        f"Sensor lab measures Nexa network [Independent Journal · {today}] :: Nexa network measurement reported today — https://news.google.com/articles/story-3",
    ))
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: rss)
    calls = []

    def read(url, query, timeout=2.5):
        calls.append(url)
        return ("Nexa network measurement reported today in the article.", today)

    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert calls == [
        "https://news.google.com/articles/story-1",
        "https://news.google.com/articles/story-3",
    ]
    assert "Independent Journal" in output
    assert "As fontes encontradas não bastam" not in output


def test_direct_news_search_uses_shared_pipeline_and_reads_at_most_two_pages(monkeypatch):
    rss = _google_news_test_rows(count=4)
    calls = []
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: rss)
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)
    monkeypatch.setattr(search_providers, "public_http_url", lambda url: url)

    def read(url, query, timeout=2.5):
        calls.append(url)
        return ("Nexa network measurement is reported in this news article.", "")

    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement news today", "1d", True
    )

    assert len(calls) == 2
    assert "Feed RSS: Publisher 1 ·" in output
    assert "Feed RSS: Publisher 2 ·" in output
    assert "Trecho da página aberta agora" in output
    prompt, system = aurora.search_answer_prompts(
        "Nexa network measurement news today", "Nexa network measurement", [output]
    )
    assert "segundo o feed, de [hora]" in prompt
    assert "segundo o feed, de [hora]" in system


def test_google_news_feed_candidate_with_failed_redirect_is_discarded(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    def read(url, query, timeout=2.5):
        calls.append(url)
        if url.endswith("story-1"):
            return ("Nexa network measurement reported today in the page.", today)
        if url.endswith("story-2"):
            raise ValueError("redirect destination failed public URL validation")
        raise ValueError("redirect destination failed public URL validation")
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached("Nexa network measurement today", "7d", False)
    assert len(calls) == 3
    assert "Publisher 2" not in output
    assert "Google Notícias, publicações" not in output
    assert "não bastam para confirmar" in output


def test_google_news_feed_date_is_accepted_when_read_page_has_no_date(monkeypatch):
    _force_provider_failure(monkeypatch)
    calls = []

    def read(url, query, timeout=2.5):
        calls.append(url)
        return ("Nexa network measurement reported today in the page.", "")

    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert len(calls) == 2
    assert "Feed RSS: Publisher 1 ·" in output
    assert "Feed RSS: Publisher 2 ·" in output
    assert "Trecho da página aberta agora" in output


def test_unread_current_pages_are_not_reported_as_stale(monkeypatch):
    _force_provider_failure(monkeypatch)

    def fail_read(*_args, **_kwargs):
        raise ValueError("page redirect rejected")

    monkeypatch.setattr(search_pipeline, "_search_page_excerpt", fail_read)
    output = aurora._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert "Não consegui ler páginas" in output
    assert "páginas abertas estavam fora" not in output


def test_stale_page_failure_reports_counts_for_each_read_filter(monkeypatch):
    from datetime import timedelta
    _force_provider_failure(monkeypatch)
    old = (datetime.now().astimezone() - timedelta(days=40)).strftime("%d/%m/%Y")
    monkeypatch.setattr(search_pipeline, "_search_page_excerpt",
                        lambda *_args, **_kwargs: ("Nexa network measurement is discussed here.", old))

    output = search_pipeline._search_public_web_uncached(
        "Nexa network measurement today", "7d", False
    )

    assert "3 fora da janela" in output
    assert "0 sem data verificável" in output
    assert "0 sem trecho legível" in output


def test_subject_specific_search_adapters_are_absent():
    source = Path(aurora.__file__).read_text().lower()
    for forbidden in ("def robux_price_answer", "def currency_rate_answer", "def minecraft_java_latest_release", "_authoritative_host"):
        assert forbidden not in source


def test_search_pipeline_reports_real_provider_and_validation_progress(monkeypatch):
    events = []
    monkeypatch.setattr(search_pipeline, "search_google_news", lambda *_args: "")
    monkeypatch.setattr(search_pipeline, "resource_worker_limit", lambda task_count, **_kwargs: 2)
    monkeypatch.setattr(search_pipeline.PUBLIC_OPENER, "open",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline fixture")))
    monkeypatch.setattr(search_pipeline, "public_http_url", lambda url: url)

    search_pipeline._search_public_web_uncached(
        "Nexa network measurement", False, False, events.append
    )

    searching = [event for event in events if event.get("stage") == "searching"]
    assert searching
    assert searching[0]["workers"] == 2
    assert {"DuckDuckGo Lite", "Bing RSS"}.issubset(set(searching[0]["tasks"]))
    assert any(event.get("finished_task") == "DuckDuckGo Lite" for event in searching)
    assert any(event.get("finished_task") == "Bing RSS" for event in searching)
    assert any(event.get("stage") == "validating" for event in events)


def test_short_cache_avoids_duplicate_search(monkeypatch):
    aurora._SEARCH_CACHE.clear()
    calls = []
    def fake(query, freshness=None, news_only=None):
        calls.append(query)
        return "cached evidence"
    monkeypatch.setattr(search_pipeline, "_search_public_web_uncached", fake)
    assert aurora.search_public_web("Nexa current value", "30d") == "cached evidence"
    assert aurora.search_public_web("Nexa current value", "30d") == "cached evidence"
    assert calls == ["Nexa current value"]
    aurora._SEARCH_CACHE.clear()


def test_search_retries_with_subject_terms_without_question_formatting():
    variants = aurora._search_query_variants(
        "Me mostra um tutorial de como jogar Starfield no Linux", ""
    )
    assert variants[0][0] == "Me mostra um tutorial de como jogar Starfield no Linux"
    assert variants[1][0] == "Starfield Linux"
    assert aurora._search_relevance(variants[1][1], "Como jogar Starfield no Linux", "") > 0


def test_version_attribute_does_not_have_to_be_repeated_in_a_result_headline():
    query = "Qual é a versão atual do Projeto Lunar?"
    assert aurora._fresh_query_terms(query) == {"projeto", "lunar"}
    assert aurora._search_relevance(query, "Projeto Lunar 4.2 já está disponível", "") == 1.0
    assert aurora._search_relevance(query, "Projeto Solar publica versão 4.2", "") == 0.0
    assert aurora._search_query_variants(query, "30d")[-1][0] == "Projeto Lunar 2026"


def test_final_search_filter_uses_subject_terms_not_instruction_words():
    query = "Me mostra um tutorial de como jogar Starfield no Linux"
    assert aurora._search_relevance(query, "Starfield Linux beginner guide", "") == 0.0
    assert aurora._result_query_relevance(query, "Starfield Linux beginner guide", "") == 1.0


def test_search_failure_keeps_the_pipeline_reason_instead_of_replacing_it():
    output = "Os provedores responderam, mas nenhum resultado passou pelos filtros de endereço público, atualidade e relação com a pergunta.\n"
    assert aurora.search_failure_summary(output, "Como jogar Starfield?") == output.splitlines()[0]
    assert "não conseguiu consultar" in aurora.search_failure_summary(
        "A busca não conseguiu consultar os provedores disponíveis (DuckDuckGo Lite: URLError; Bing RSS: URLError).",
        "Qual é a versão atual?",
    )
