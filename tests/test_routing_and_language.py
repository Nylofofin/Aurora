# SPDX-License-Identifier: GPL-3.0-only
import threading
from concurrent.futures import Future

import aurora
import aurora_core.routing as routing


def test_new_wake_request_is_not_dropped_while_cancelled_inference_exits(monkeypatch):
    monkeypatch.setattr(routing, "parse_local_command", lambda _prompt: None)
    monkeypatch.setattr(routing, "local_datetime_answer", lambda _prompt: "Agora são dez horas.")

    class Voice:
        def __init__(self):
            self.request_active = threading.Event()
            self.request_active.set()
            self.speaking = False

    class Orb:
        def isVisible(self): return True
        def set_mode(self, _mode): pass
        def reveal(self, _mode): pass

    class InferenceStillExiting:
        cancelled = True
        def isRunning(self): return True

    class ServiceStub:
        voice = Voice()
        orb = Orb()
        inf = InferenceStillExiting()
        cfg = {"model": "gemma3:1b"}
        context_history = []
        activity_generation = 2
        request_generation = 4
        response_language = "Português brasileiro"

        def quick_summary_done(self, text, generation):
            self.completed = (text, generation)

    service = ServiceStub()
    routing.route_request(service, "Que horas são?")

    assert service.completed == ("Agora são dez horas.", 5)


def test_non_cancelled_active_inference_still_blocks_duplicate_transcript(monkeypatch):
    class Voice:
        request_active = threading.Event()
    Voice.request_active.set()

    class Inference:
        cancelled = False
        def isRunning(self): return True

    class ServiceStub:
        voice = Voice()
        inf = Inference()
        request_generation = 4
        activity_generation = 2

    service = ServiceStub()
    routing.route_request(service, "Que horas são?")

    assert service.request_generation == 4
    assert service.activity_generation == 2


def test_small_talk_and_personal_advice_do_not_trigger_web_search():
    for prompt in (
        "Como você tá?",
        "Como foi seu dia?",
        "O que você acha disso?",
        "Quem é você?",
        "Qual sua opinião sobre isso?",
        "Preciso desabafar um pouco.",
        "O que eu faço agora?",
    ):
        assert not aurora.factual_web_intent(prompt), prompt


def test_arithmetic_questions_do_not_trigger_web_search():
    for prompt in (
        "Quanto é 15 vezes 12?",
        "Quanto dá 10,5 dividido por 2?",
        "Calcule 7 + 8",
        "Qual é 15% de 200?",
    ):
        assert not aurora.factual_web_intent(prompt), prompt


def test_news_and_how_to_requests_route_to_research_without_search_verbs():
    assert aurora.research_request_intent("Notícias nacionais e internacionais")
    assert aurora.research_request_intent("Me mostra um tutorial para configurar um roteador")
    assert aurora.guided_learning_intent("Como jogar um jogo de estratégia?")
    assert aurora.factual_web_intent("Como jogar um jogo de estratégia?" )
    assert aurora.news_search_intent("Quais são as notícias internacionais hoje?")


def test_local_action_language_takes_precedence_over_automatic_factual_search(monkeypatch):
    monkeypatch.setattr(routing, "parse_local_command", lambda _prompt: None)
    monkeypatch.setattr(routing, "local_datetime_answer", lambda _prompt: "")
    monkeypatch.setattr(routing, "calculate_local_expression", lambda _prompt: None)
    monkeypatch.setattr(routing, "search_intent", lambda _prompt: "")

    class Voice:
        def __init__(self):
            self.request_active = threading.Event()
            self.request_active.set()
            self.speaking = False

    class Orb:
        def isVisible(self): return True
        def set_mode(self, _mode): pass
        def reveal(self, _mode): pass

    class Signal:
        def connect(self, _callback, *_args): pass

    class FakeInference:
        def __init__(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs
            self.sentence = self.search = self.progress = self.approval = self.error = self.result = Signal()

    monkeypatch.setattr(routing, "Inference", FakeInference)

    class Service:
        voice = Voice()
        orb = Orb()
        inf = None
        cfg = {"model": "gemma3:1b", "agent_model": "gemma4:e2b"}
        context_history = []
        activity_generation = 0
        request_generation = 0
        response_language = "Português brasileiro"
        voice = type("VoiceStub", (), {"request_active": threading.Event()})()
        voice.request_active.set()

        def start_background_request(self, _request):
            raise AssertionError("A pergunta de ação local não deve abrir a busca web")
        def start_inference(self, inference, generation):
            self.started = (inference, generation)

    service = Service()
    routing.route_request(service, "Como abro o terminal?")

    inference, _ = service.started
    assert inference.kwargs["model"] == "gemma4:e2b"
    assert inference.kwargs["use_tools"] is True

    for prompt in ("Como está meu computador hoje?", "Meu PC tem quanta memória livre?"):
        routing.route_request(service, prompt)
        inference, _ = service.started
        assert inference.kwargs["model"] == "gemma4:e2b", prompt
        assert inference.kwargs["use_tools"] is True, prompt


def test_agent_action_cue_does_not_mistake_topic_nouns_for_commands():
    assert routing._agent_action_intent("como abro o terminal")
    assert routing._agent_action_intent("quero abrir o navegador")
    assert not routing._agent_action_intent("quais sao os eventos de tecnologia hoje")
    assert not routing._agent_action_intent("qual foi o aumento do setor este ano")


def test_explicit_local_context_prefers_the_agent_without_turning_topics_into_commands():
    assert routing._local_context_intent("como esta meu computador hoje")
    assert routing._local_context_intent("meu pc tem quanta memoria livre")
    assert routing._local_context_intent("quais programas estao instalados")
    assert not routing._local_context_intent("noticias sobre computadores hoje")
    assert not routing._local_context_intent("qual o melhor computador para jogos")


def test_local_hardware_question_bypasses_model_acknowledgement(monkeypatch):
    class Voice:
        def __init__(self):
            self.request_active = threading.Event()
            self.request_active.set()
            self.speaking = False

    class Orb:
        def isVisible(self): return True
        def set_mode(self, _mode): pass
        def reveal(self, _mode): pass

    class Service:
        voice = Voice()
        orb = Orb()
        inf = None
        context_history = []
        activity_generation = 0
        request_generation = 0
        response_language = "Português brasileiro"
        voice = type("VoiceStub", (), {"request_active": threading.Event()})()
        voice.request_active.set()

        def run_local_action(self, name, args): self.action = (name, args)
        def start_inference(self, *_args): raise AssertionError("hardware lookup must skip Gemma")
        def start_background_request(self, *_args): raise AssertionError("hardware lookup must stay local")

    monkeypatch.setattr(routing, "parse_local_command", aurora.parse_local_command)
    service = Service()
    routing.route_request(service, "Quais são os componentes do meu PC?")

    assert service.action == ("system_info", {})


def test_international_news_scope_is_not_mistaken_for_the_topic():
    query = "notícias internacionais de tecnologia hoje"
    assert aurora._fresh_query_terms(query) == {"internacionais", "tecnologia"}
    assert aurora._fresh_query_terms("World Cup") == {"world", "cup"}
    assert aurora._news_result_relevance(
        query, "Notícias internacionais sobre tecnologia", "Cobertura do setor"
    ) > 0
    assert aurora._news_result_relevance(
        "notícias internacionais", "International news roundup", "World headlines"
    ) > 0
    assert aurora.international_news_only("notícias internacionais")
    assert not aurora.international_news_only("notícias nacionais e internacionais")
    assert aurora._news_result_relevance(
        "notícias nacionais e internacionais", "Principais notícias do Brasil e do mundo", ""
    ) > 0


def test_response_language_can_be_switched_and_reset_in_portuguese():
    assert aurora.requested_response_language("Fale comigo em inglês") == "English"
    assert aurora.requested_response_language("Responda em espanhol") == "Spanish"
    assert aurora.requested_response_language("Muda para francês") == "French"
    assert aurora.requested_response_language("Volta para português brasileiro") == "Português brasileiro"
    assert aurora.requested_response_language("Qual sua opinião?") is None


def test_system_and_search_prompts_use_selected_response_language():
    assert "Responda em English" in aurora.assistant_system_prompt(response_language="English")
    assert "Você é Luna" in aurora.assistant_system_prompt(assistant_name="Luna")
    assert "prefere o nome Nylo" in aurora.assistant_system_prompt(user_name="Nylo")
    prompt, system = aurora.search_answer_prompts(
        "latest world news", "world news", ["International briefing"], response_language="English"
    )
    assert "em English" in prompt
    assert "em English" in system
    tutorial, _ = aurora.search_answer_prompts(
        "Tutorial: como jogar um jogo de exemplo", "jogo de exemplo", ["Passo inicial"], response_language="Português brasileiro"
    )
    assert "até quatro passos curtos e práticos" in tutorial
