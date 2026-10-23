from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from aurora_core.ui.research_card import ResearchCard


def test_research_card_updates_stages_and_shows_source_results(monkeypatch):
    app = QApplication.instance() or QApplication([])
    card = ResearchCard()
    monkeypatch.setattr(card, "_show_near", lambda _anchor: None)
    card.begin(3, "Compare current sources about two topics", None)
    card.update_progress(3, {
        "stage": "searching", "tasks": ["topic A", "topic B"],
        "workers": 2, "completed": 1, "total": 2,
        "finished_task": "topic B",
        "result": "Search header\nA useful source [publisher.example · 23/10/2026] :: Current source excerpt. — https://publisher.example/news",
    })

    assert card.stage_label.text() == "Pesquisando em paralelo · 1/2 etapas"
    assert card.progress.value() == 37
    assert len(card._live_sources) == 1
    assert card._live_sources[0]["host"] == "publisher.example"
    assert card._live_sources[0]["published"] == "23/10/2026"
    card.hide()
    app.processEvents()


def test_research_card_ignores_stale_generation_results(monkeypatch):
    app = QApplication.instance() or QApplication([])
    card = ResearchCard()
    monkeypatch.setattr(card, "_show_near", lambda _anchor: None)
    card.begin(5, "Current query", None)
    card.update_progress(4, {"stage": "complete", "result": "old"})

    assert card.stage_label.text() == "Pesquisando em paralelo"
    assert card.progress.value() == 8
    card.hide()
    app.processEvents()


def test_research_card_consumes_live_pipeline_sources_and_read_stage(monkeypatch):
    app = QApplication.instance() or QApplication([])
    card = ResearchCard()
    monkeypatch.setattr(card, "_show_near", lambda _anchor: None)
    card.begin(8, "Recent technology news", None)
    card.update_progress(8, {
        "stage": "searching", "tasks": ["Bing RSS"], "workers": 1,
        "completed": 1, "total": 1, "finished_task": "Bing RSS",
        "sources": [{"title": "New release", "host": "publisher.example",
                     "snippet": "A real source", "url": "https://publisher.example/news",
                     "published": "23/10/2026"}],
    })
    assert len(card._live_sources) == 1
    assert "publisher.example" in card.source_layout.itemAt(0).widget().findChildren(type(card.query_label))[1].text()
    card.update_progress(8, {"stage": "reading", "completed": 1, "total": 2})
    assert card.stage_label.text() == "Abrindo páginas verificadas · 1/2"
    card.hide()
    app.processEvents()


def test_research_card_shows_local_parallel_inspection_without_web_sources(monkeypatch):
    app = QApplication.instance() or QApplication([])
    card = ResearchCard()
    monkeypatch.setattr(card, "_show_near", lambda _anchor: None)
    card.begin(9, "Consulte hardware e volume", None, mode="local")
    card.update_progress(9, {
        "mode": "local", "stage": "executing", "tasks": ["Consultar hardware", "Consultar volume"],
        "workers": 2, "completed": 1, "total": 2, "finished_task": "Consultar volume",
    })

    assert card.source_heading.isHidden()
    assert card.source_area.isHidden()
    assert card.stage_label.text() == "Consultando ferramentas locais · 1/2"
    assert card.worker_labels[1].text().endswith("concluída")
    card.hide()
    app.processEvents()


def test_research_card_keeps_untrusted_labels_as_plain_text(monkeypatch):
    app = QApplication.instance() or QApplication([])
    card = ResearchCard()
    monkeypatch.setattr(card, "_show_near", lambda _anchor: None)
    card.begin(12, "<b>Consulta</b>", None)
    card.set_sources(12, [{
        "title": "<img src='https://invalid.example/pixel'> Fonte",
        "host": "fonte.example", "url": "https://fonte.example/",
    }])

    source_title = card.source_layout.itemAt(0).widget().findChildren(QLabel)[0]
    assert card.query_label.text() == "<b>Consulta</b>"
    assert source_title.text().startswith("<img")
    assert card.query_label.textFormat() == Qt.TextFormat.PlainText
    assert source_title.textFormat() == Qt.TextFormat.PlainText
    card.hide()
    app.processEvents()


def test_card_summary_preview_stops_at_sentence_or_word_boundary():
    first_sentence = "Esta frase termina com sentido."
    text = first_sentence + " " + ("Uma segunda frase longa sem pausa " * 20)

    assert ResearchCard._summary_preview(text, limit=40) == first_sentence

    clipped = ResearchCard._summary_preview("palavra " * 20, limit=24)
    assert clipped.endswith("…")
    assert not clipped.endswith("palavr…")
