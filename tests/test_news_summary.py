from datetime import datetime

from aurora_core.web.news_summary import format_news_digest
from scripts.eval_search import EvalService


def test_news_digest_preserves_headline_and_publisher_without_model_paraphrase():
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    items = [
        {
            "title": "Brasil avança em IA, mas Chile lidera ranking de infraestrutura",
            "host": "bloomberglinea.com.br",
            "published": today,
        },
        {
            "title": "Inteligência artificial personaliza ciclos de lavagem da LG",
            "host": "prnewswire.com",
            "published": today,
        },
    ]

    answer = format_news_digest(items, "1d")

    assert items[0]["title"] in answer
    assert "Chile lidera" in answer
    assert "bloomberglinea.com.br" in answer
    assert "prnewswire.com" in answer
    assert "Brasil lidera ranking" not in answer


def test_current_news_digest_requires_two_recent_independent_sources():
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    one_source = [{"title": "Notícia de tecnologia", "host": "publisher.example", "published": today}]

    assert format_news_digest(one_source, "1d") == "Não consegui confirmar notícias recentes sobre esse assunto."


def test_news_service_speaks_verified_headlines_without_starting_inference():
    today = datetime.now().astimezone().strftime("%d/%m/%Y")
    service = EvalService({})
    service.current_prompt = "Quais notícias de inteligência artificial hoje?"
    service.request_generation = 3
    output = "\n".join((
        "Resultados combinados:",
        f"Brasil avança em IA, mas Chile lidera ranking de infraestrutura [bloomberglinea.com.br · {today}] :: Índice de infraestrutura de inteligência artificial da Cepal. — https://bloomberglinea.com.br/story",
        f"Inteligência artificial personaliza ciclos de lavagem da LG [prnewswire.com · {today}] :: A IA ajuda a personalizar ciclos. — https://prnewswire.com/story",
    ))

    service.quick_search_done(service.current_prompt, output, service.request_generation)

    assert service.done
    assert len(service.speaker.parts) == 1
    assert "Chile lidera" in service.speaker.parts[0]
    assert "Brasil lidera ranking" not in service.speaker.parts[0]
    assert service.inferences == []
