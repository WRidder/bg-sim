"""Latest-wins coalescing of ``POST /api/check/block`` (P2.1).

The editor checks a block on every debounced keystroke. A slower answer for an
older source must never reach a client. A scripted worker gates ``block.check``
on an event and records every source it receives, so these tests prove the worker
call count, which answer each HTTP request gets, and that unrelated keys (another
client or ref) are not coalesced with each other.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

import httpx

from bgsim_server.app import create_app
from bgsim_server.worker import KIND_JSON, encode_frame, read_frame

TIMEOUT = 5.0


def _marker(source: str) -> int:
    """The marker encoded in a scripted source name (``s3`` -> 3), else -1."""
    return int(source[1:]) if source[:1] in {"a", "b", "s"} and source[1:].isdigit() else -1


def _result(source: str) -> dict[str, Any]:
    """A contract-valid ``block.check`` result that identifies its source."""
    return {
        "diagnostics": [],
        "interface": {
            "constants": [
                {"name": "Marker", "type": "Int", "default": _marker(source), "structural": False}
            ],
            "parameters": [],
            "inputs": [],
            "outputs": [],
            "ports": [],
            "variables": [],
            "causality": [],
        },
    }


class GatedCheckWorker:
    """A scripted worker: ``block.check`` waits on ``release`` before answering."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.release = asyncio.Event()
        self.calls: list[str] = []
        self.fail_sources: set[str] = set()
        self._task: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._serve(), name="gated-check-worker")

    async def stop(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _serve(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self._writer = writer
        try:
            while True:
                frame = await read_frame(reader)
                if frame is None:
                    break
                message = json.loads(frame[1])
                method = message.get("method")
                if method == "ping":
                    await self._send(
                        {
                            "id": message["id"],
                            "result": {"version": "0.1.0", "julia": "gated", "warm": True},
                        }
                    )
                elif method == "block.check":
                    params = message.get("params") or {}
                    source = str(params.get("source"))
                    self.calls.append(source)
                    await self.release.wait()
                    if source in self.fail_sources:
                        await self._send(
                            {
                                "id": message["id"],
                                "error": {"message": f"check failed: {source}", "diagnostics": []},
                            }
                        )
                    else:
                        await self._send({"id": message["id"], "result": _result(source)})
                else:
                    await self._send(
                        {
                            "id": message["id"],
                            "error": {
                                "message": f"method {method!r} is not scripted here",
                                "diagnostics": [],
                            },
                        }
                    )
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def _send(self, message: dict[str, Any]) -> None:
        writer = self._writer
        if writer is None:
            return
        writer.write(encode_frame(KIND_JSON, json.dumps(message).encode("utf-8")))
        await writer.drain()


async def _wait_ready(client: httpx.AsyncClient, timeout: float = TIMEOUT) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if (await client.get("/api/health")).json()["worker"] == "ready":
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"the scripted worker did not become ready within {timeout:g} s")


async def _wait_until(predicate, timeout: float = TIMEOUT) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"condition not reached within {timeout:g} s")


def _app(fake_settings, workers: list[GatedCheckWorker]):
    def factory(port: int) -> GatedCheckWorker:
        worker = GatedCheckWorker(port)
        workers.append(worker)
        return worker

    return create_app(fake_settings, worker_factory=factory)


async def _post(client: httpx.AsyncClient, source: str, ref: str | None) -> httpx.Response:
    return await client.post("/api/check/block", json={"source": source, "ref": ref})


def _marker_of(response: httpx.Response) -> int:
    assert response.status_code == 200, response.text
    return int(response.json()["interface"]["constants"][0]["default"])


async def test_five_rapid_checks_use_two_worker_calls_and_only_the_newest_answer(
    fake_settings,
) -> None:
    workers: list[GatedCheckWorker] = []
    app = _app(fake_settings, workers)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await _wait_ready(client)
            worker = workers[0]
            coalescer = app.state.block_check_coalescer

            # Five rapid requests, one event-loop turn apart. The gated worker
            # cannot finish the first call, so requests 2-5 replace the single
            # queued call: one running source (s1) and the newest one (s5).
            requests = [asyncio.create_task(_post(client, "s1", "project:Foo"))]
            await _wait_until(lambda: coalescer.stats()["waiters"] == 1)
            for index in range(2, 6):
                requests.append(asyncio.create_task(_post(client, f"s{index}", "project:Foo")))
                await _wait_until(lambda count=index: coalescer.stats()["waiters"] == count)
            worker.release.set()
            responses = await asyncio.gather(*requests)

            # Every caller gets the newest answer; the stale s1 result is dropped.
            assert [_marker_of(response) for response in responses] == [5, 5, 5, 5, 5]
            assert worker.calls == ["s1", "s5"], (
                "five rapid requests must cost at most two worker calls"
            )
            assert coalescer.stats() == {"keys": 0, "running": 0, "pending": 0, "waiters": 0}

            # A different ref is a different key and is not delayed by Foo.
            other = await _post(client, "s6", "project:Bar")
            assert _marker_of(other) == 6
            assert worker.calls == ["s1", "s5", "s6"]

            # A request that arrives after the previous one finished is a new call.
            later = await _post(client, "s7", "project:Foo")
            assert _marker_of(later) == 7
            assert worker.calls == ["s1", "s5", "s6", "s7"]


async def test_coalescing_is_per_client_and_per_ref(fake_settings) -> None:
    workers: list[GatedCheckWorker] = []
    app = _app(fake_settings, workers)
    async with app.router.lifespan_context(app):
        transport_a = httpx.ASGITransport(app=app, client=("10.0.0.1", 1001))
        transport_b = httpx.ASGITransport(app=app, client=("10.0.0.2", 2002))
        async with (
            httpx.AsyncClient(transport=transport_a, base_url="http://test") as client_a,
            httpx.AsyncClient(transport=transport_b, base_url="http://test") as client_b,
        ):
            await _wait_ready(client_a)
            worker = workers[0]
            coalescer = app.state.block_check_coalescer

            # Two clients, two requests per key, staggered so the first source
            # of each key is the running call and the second is the queued one.
            requests = [asyncio.create_task(_post(client_a, "a1", "project:Foo"))]
            await _wait_until(lambda: coalescer.stats()["waiters"] == 1)
            requests.append(asyncio.create_task(_post(client_a, "a2", "project:Foo")))
            await _wait_until(lambda: coalescer.stats()["waiters"] == 2)
            requests.append(asyncio.create_task(_post(client_b, "b1", "project:Foo")))
            await _wait_until(lambda: coalescer.stats()["waiters"] == 3)
            requests.append(asyncio.create_task(_post(client_b, "b2", "project:Foo")))
            await _wait_until(lambda: coalescer.stats()["waiters"] == 4)
            worker.release.set()
            responses = await asyncio.gather(*requests)

            # Two keys, one call each plus one newest call each: four calls.
            assert sorted(worker.calls) == ["a1", "a2", "b1", "b2"]
            assert [_marker_of(response) for response in responses] == [2, 2, 2, 2]
            assert coalescer.stats()["keys"] == 0


async def test_a_failed_newest_check_is_reported_and_the_stale_success_dropped(
    fake_settings,
) -> None:
    workers: list[GatedCheckWorker] = []
    app = _app(fake_settings, workers)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await _wait_ready(client)
            worker = workers[0]
            worker.fail_sources = {"s2"}
            coalescer = app.state.block_check_coalescer

            requests = [asyncio.create_task(_post(client, "s1", "project:Foo"))]
            await _wait_until(lambda: coalescer.stats()["waiters"] == 1)
            requests.append(asyncio.create_task(_post(client, "s2", "project:Foo")))
            await _wait_until(lambda: coalescer.stats()["waiters"] == 2)
            worker.release.set()
            responses = await asyncio.gather(*requests)

            assert [response.status_code for response in responses] == [422, 422]
            assert {response.json()["message"] for response in responses} == {"check failed: s2"}
            assert worker.calls == ["s1", "s2"]
            assert coalescer.stats()["keys"] == 0
