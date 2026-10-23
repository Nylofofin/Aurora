from aurora_core.web.orchestra import (
    local_parallel_tool_calls, local_worker_limit, plan_research_subagents,
    resource_worker_limit,
)


def test_resource_budget_reduces_workers_under_load_or_low_memory():
    assert resource_worker_limit(4, load_per_cpu=0.1, available_ram=12 * 1024**3, cpu_count=8) == 3
    assert resource_worker_limit(4, load_per_cpu=0.6, available_ram=12 * 1024**3, cpu_count=8) == 2
    assert resource_worker_limit(4, load_per_cpu=0.1, available_ram=1 * 1024**3, cpu_count=8) == 1
    assert resource_worker_limit(4, load_per_cpu=0.1, available_ram=12 * 1024**3, cpu_count=2) == 1
    assert resource_worker_limit(1, load_per_cpu=0.0, available_ram=12 * 1024**3, cpu_count=8) == 1


def test_local_workers_are_capped_and_mutations_never_fan_out():
    assert local_worker_limit(4, load_per_cpu=0.1, available_ram=12 * 1024**3, cpu_count=8) == 2
    allowed = [
        {"function": {"name": "get_system_info", "arguments": {}}},
        {"function": {"name": "inspect_accessible_windows", "arguments": {"application": "Editor"}}},
    ]
    assert local_parallel_tool_calls(allowed)
    assert not local_parallel_tool_calls(allowed[:1])
    assert not local_parallel_tool_calls(allowed + [
        {"function": {"name": "open_application", "arguments": {"command": "Editor"}}}
    ])
    assert not local_parallel_tool_calls([
        {"function": {"name": "volume_control", "arguments": {"action": "set", "value": 20}}},
        {"function": {"name": "get_system_info", "arguments": {}}},
    ])


def test_explicit_comparison_becomes_independent_research_subagents():
    tasks = plan_research_subagents("Compare Gemma 3 e Gemma 4")
    assert [task.query for task in tasks] == ["Gemma 3", "Gemma 4"]
    assert [task.name for task in tasks] == ["Subagente 1 · Gemma 3", "Subagente 2 · Gemma 4"]


def test_multiple_explicit_questions_are_split_but_simple_lists_are_not():
    tasks = plan_research_subagents("Quem criou o projeto Orion? Qual é a versão atual do Python?")
    assert [task.query for task in tasks] == ["Quem criou o projeto Orion", "Qual é a versão atual do Python"]
    assert len(plan_research_subagents("Quem criou o projeto X? E a versão atual?")) == 1
    assert len(plan_research_subagents("Notícias de ciência e tecnologia hoje")) == 1


def test_subagent_plan_is_bounded_and_conserves_ambiguous_requests():
    ambiguous = "Pesquise preço, desempenho, disponibilidade e opiniões sobre o produto"
    assert len(plan_research_subagents(ambiguous)) == 1
    many = plan_research_subagents("Quem é A? Quem é B? Quem é C? Quem é D?")
    assert len(many) <= 3
