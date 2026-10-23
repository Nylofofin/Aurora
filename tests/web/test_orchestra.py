from aurora_core.web.orchestra import resource_worker_limit


def test_resource_budget_reduces_workers_under_load_or_low_memory():
    assert resource_worker_limit(4, load_per_cpu=0.1, available_ram=12 * 1024**3, cpu_count=8) == 3
    assert resource_worker_limit(4, load_per_cpu=0.6, available_ram=12 * 1024**3, cpu_count=8) == 2
    assert resource_worker_limit(4, load_per_cpu=0.1, available_ram=1 * 1024**3, cpu_count=8) == 1
    assert resource_worker_limit(4, load_per_cpu=0.1, available_ram=12 * 1024**3, cpu_count=2) == 1
    assert resource_worker_limit(1, load_per_cpu=0.0, available_ram=12 * 1024**3, cpu_count=8) == 1
