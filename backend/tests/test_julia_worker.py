"""The real Julia worker (plan 6): marked `julia`, deselected by default.

Run with:  uv run --directory backend pytest -q -m julia -s
"""

from __future__ import annotations

import time

import pytest

from bgsim_server.worker import WorkerRpcError, WorkerSupervisor

pytestmark = pytest.mark.julia

COLD_START_TIMEOUT = 600.0  # a cold `using BGSim` may recompile the package first


async def test_real_worker_ping_cold_start_and_protocol_edges(real_settings) -> None:
    supervisor = WorkerSupervisor(real_settings)
    started = time.perf_counter()
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=COLD_START_TIMEOUT)
        cold_start = time.perf_counter() - started
        assert supervisor.state == "ready"

        first_started = time.perf_counter()
        result = await supervisor.call("ping")
        first_round_trip = time.perf_counter() - first_started
        assert result["version"] == "0.1.0"
        assert result["julia"].startswith("1.13")
        assert result["warm"] is True

        warm_times = []
        for _ in range(5):
            tick = time.perf_counter()
            assert (await supervisor.call("ping"))["warm"] is True
            warm_times.append(time.perf_counter() - tick)
        warm_times.sort()

        with pytest.raises(WorkerRpcError) as info:
            await supervisor.call("model.check", {"model": {}, "projectDir": "."})
        assert "not implemented" in str(info.value)
        assert info.value.diagnostics == []

        await supervisor.send_binary(b"\x00\x01\x02")  # must be rejected cleanly
        assert (await supervisor.call("ping"))["warm"] is True

        log = real_settings.worker_log_path.read_text(encoding="utf-8", errors="replace")
        assert "[BGSim.Worker] connected; serving frames" in log

        print(f"\njulia cold start to ready: {cold_start:.2f} s")
        print(f"julia ping round-trip: first {first_round_trip * 1000:.2f} ms, "
              f"warm median {warm_times[len(warm_times) // 2] * 1000:.2f} ms "
              f"(min {warm_times[0] * 1000:.2f} ms)")
    finally:
        await supervisor.stop()
