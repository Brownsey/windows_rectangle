"""Tests for windows_rectangle.core.cleanup."""

from windows_rectangle.core.cleanup import CleanupRegistry


def test_register_and_run_invokes_in_lifo_order():
    log = []
    r = CleanupRegistry()
    r.register(lambda: log.append("first_registered"))
    r.register(lambda: log.append("second_registered"))
    r.register(lambda: log.append("third_registered"))
    r.run()
    assert log == ["third_registered", "second_registered", "first_registered"]


def test_run_returns_count():
    r = CleanupRegistry()
    r.register(lambda: None)
    r.register(lambda: None)
    assert r.run() == 2


def test_run_is_idempotent():
    log = []
    r = CleanupRegistry()
    r.register(lambda: log.append("x"))
    r.run()
    r.run()  # second call no-op
    assert log == ["x"]


def test_exception_in_handler_doesnt_stop_others():
    log = []
    r = CleanupRegistry()
    r.register(lambda: log.append("a"))
    r.register(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    r.register(lambda: log.append("c"))
    r.run()
    # c (last registered) runs first, throws nothing.
    # then the bad one runs, exception swallowed.
    # then a runs.
    assert log == ["c", "a"]


def test_context_manager_runs_on_exit():
    log = []
    with CleanupRegistry() as r:
        r.register(lambda: log.append("done"))
    assert log == ["done"]


def test_context_manager_runs_even_on_exception():
    log = []
    try:
        with CleanupRegistry() as r:
            r.register(lambda: log.append("done"))
            raise ValueError("ugh")
    except ValueError:
        pass
    assert log == ["done"]


def test_register_after_run_executes_immediately():
    log = []
    r = CleanupRegistry()
    r.run()  # mark as done
    r.register(lambda: log.append("late"))
    assert log == ["late"]


def test_len_tracks_stack_size():
    r = CleanupRegistry()
    assert len(r) == 0
    r.register(lambda: None)
    r.register(lambda: None)
    assert len(r) == 2
    r.run()
    assert len(r) == 0
