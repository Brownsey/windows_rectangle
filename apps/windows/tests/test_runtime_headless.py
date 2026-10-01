"""Headless scheduling and shutdown without Qt or global input."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from windows_rectangle import __main__ as entry
from windows_rectangle.app import build
from windows_rectangle.core.actionbus import ActionBus
from windows_rectangle.core.actions import Action
from windows_rectangle.core.dispatcher import Dispatcher
from windows_rectangle.ports.config_store import Settings

from .conftest import FakeWindowManager


class Context:
    def __init__(self, *, prune_interval=60.0):
        self.bus = ActionBus()
        self.wake_ui = None
        self.prune_interval = prune_interval
        self.drains = []
        self.maintenance_calls = []
        self.actions = []
        self.active = False
        self.on_drain = None
        self.on_action = None

    def drain_actions(self):
        self.drains.append(time.perf_counter())
        if self.on_drain is not None:
            self.on_drain()
        return self.bus.drain(self.on_action or self.actions.append, limit=16)

    def maintenance(self, now=None):
        self.maintenance_calls.append(time.perf_counter())
        return 0

    def has_pending_work(self):
        return bool(self.bus.pending() or self.active)


def fake_signals(monkeypatch):
    previous = object()
    handlers = {signal.SIGINT: previous, signal.SIGTERM: previous}
    monkeypatch.setattr(entry.signal, "getsignal", handlers.get)
    monkeypatch.setattr(
        entry.signal, "signal", lambda sig, callback: handlers.__setitem__(sig, callback)
    )
    return handlers, previous


def test_headless_idle_does_not_drain_at_30hz_and_restores_callbacks(monkeypatch):
    handlers, previous = fake_signals(monkeypatch)
    ctx = Context()
    waits = []

    class Event:
        def clear(self):
            pass

        def set(self):
            pass

        def wait(self, timeout):
            waits.append(timeout)
            handlers[signal.SIGINT](signal.SIGINT, None)
            return False

    monkeypatch.setattr(threading, "Event", Event)
    assert entry._run_headless(ctx) == 0
    assert waits == [0.25]
    assert len(ctx.drains) == 1
    assert len(ctx.maintenance_calls) == 1
    assert ctx.bus.on_submit is None
    assert ctx.wake_ui is None
    assert handlers[signal.SIGINT] is previous
    assert handlers[signal.SIGTERM] is previous


def test_headless_worker_action_wakes_idle_loop_and_dispatches_on_main_thread(monkeypatch):
    handlers, _ = fake_signals(monkeypatch)
    ctx = Context()
    gui_thread = threading.get_ident()
    submitted = []
    dispatched = []

    def consume(action):
        dispatched.append((action, threading.get_ident(), time.perf_counter()))
        handlers[signal.SIGINT](signal.SIGINT, None)

    ctx.on_action = consume

    def produce():
        submitted.append(time.perf_counter())
        ctx.bus.submit(Action.LEFT_HALF)

    worker = threading.Timer(0.04, produce)
    fallback = threading.Timer(0.5, lambda: handlers[signal.SIGINT](signal.SIGINT, None))
    worker.start()
    fallback.start()
    try:
        assert entry._run_headless(ctx) == 0
    finally:
        worker.join(timeout=1)
        fallback.cancel()
        fallback.join(timeout=1)
    assert dispatched[0][:2] == (Action.LEFT_HALF, gui_thread)
    assert dispatched[0][2] - submitted[0] < 0.1


def test_headless_drag_input_wake_starts_active_polling(monkeypatch):
    handlers, _ = fake_signals(monkeypatch)
    ctx = Context()
    activated = []

    def on_drain():
        if ctx.active:
            activated.append(time.perf_counter())
            handlers[signal.SIGINT](signal.SIGINT, None)

    ctx.on_drain = on_drain

    def press():
        ctx.active = True
        ctx.wake_ui()

    worker = threading.Timer(0.04, press)
    fallback = threading.Timer(0.5, lambda: handlers[signal.SIGINT](signal.SIGINT, None))
    worker.start()
    fallback.start()
    try:
        assert entry._run_headless(ctx) == 0
    finally:
        worker.join(timeout=1)
        fallback.cancel()
        fallback.join(timeout=1)
    assert len(activated) == 1


def test_headless_work_arriving_during_drain_is_not_lost(monkeypatch):
    handlers, _ = fake_signals(monkeypatch)
    ctx = Context()
    submitted = False

    def during_drain():
        nonlocal submitted
        if not submitted:
            submitted = True
            ctx.bus.submit(Action.RIGHT_HALF)
        elif ctx.actions:
            handlers[signal.SIGINT](signal.SIGINT, None)

    ctx.on_drain = during_drain
    fallback = threading.Timer(0.5, lambda: handlers[signal.SIGINT](signal.SIGINT, None))
    fallback.start()
    try:
        assert entry._run_headless(ctx) == 0
    finally:
        fallback.cancel()
        fallback.join(timeout=1)
    assert ctx.actions == [Action.RIGHT_HALF]
    assert len(ctx.drains) >= 2
    assert ctx.drains[1] - ctx.drains[0] < 0.1


def test_headless_active_work_retains_33ms_polling(monkeypatch):
    handlers, _ = fake_signals(monkeypatch)
    ctx = Context()
    ctx.active = True
    waits = []

    class Event:
        def clear(self):
            pass

        def set(self):
            pass

        def wait(self, timeout):
            waits.append(timeout)
            if len(waits) == 3:
                handlers[signal.SIGINT](signal.SIGINT, None)
            return False

    monkeypatch.setattr(threading, "Event", Event)
    assert entry._run_headless(ctx) == 0
    assert len(ctx.drains) >= 3
    assert all(0 < timeout <= 1 / 30 + 0.000001 for timeout in waits)


def test_headless_real_sigint_exits_within_idle_wait_cap():
    root = Path(__file__).resolve().parents[3]
    code = """
import signal, threading, time
from windows_rectangle.__main__ import _run_headless
from windows_rectangle.core.actionbus import ActionBus
class Context:
    def __init__(self):
        self.bus = ActionBus()
        self.wake_ui = None
        self.prune_interval = 60.0
    def drain_actions(self): pass
    def maintenance(self, now=None): pass
    def has_pending_work(self): return False
timer = threading.Timer(0.02, lambda: signal.raise_signal(signal.SIGINT))
timer.start()
started = time.perf_counter()
_run_headless(Context())
timer.join()
print(time.perf_counter() - started)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "apps/windows")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert float(result.stdout.strip()) < 0.6


def test_headless_maintenance_deadline_tracks_actual_prune(monkeypatch):
    handlers, _ = fake_signals(monkeypatch)
    ctx = build(Settings(shortcuts={}), FakeWindowManager())
    ctx.prune_interval = 0.04
    clock = type("Clock", (), {"now": 0.0})()
    prunes = []
    monkeypatch.setattr(
        entry, "time", type("Time", (), {"monotonic": staticmethod(lambda: clock.now)})()
    )
    monkeypatch.setattr(
        Dispatcher,
        "prune_stale_state",
        lambda _self: prunes.append(clock.now) or 0,
    )

    class Event:
        def __init__(self):
            self.waits = 0

        def clear(self):
            pass

        def set(self):
            pass

        def wait(self, timeout):
            self.waits += 1
            ctx.bus.submit(Action.CENTER)  # Frequent actions must not move the deadline.
            clock.now += timeout + (0.010 if self.waits == 1 else 0.005)
            if self.waits == 3:
                handlers[signal.SIGINT](signal.SIGINT, None)
            return False

    monkeypatch.setattr(threading, "Event", Event)
    assert entry._run_headless(ctx) == 0
    assert len(prunes) == 3  # Startup and two completed intervals.
