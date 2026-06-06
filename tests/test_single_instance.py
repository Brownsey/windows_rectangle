"""Tests for windows_rectangle.adapters.single_instance.

The Windows ctypes path needs a Windows runtime + would mutate kernel state,
so we only test MemorySingleInstance + helpers here.
"""

import pytest

from windows_rectangle.adapters.single_instance import (
    MemorySingleInstance,
    best_available,
)
from windows_rectangle.ports.single_instance import DEFAULT_MUTEX_NAME


@pytest.fixture(autouse=True)
def isolate_memory_lock():
    """Ensure MemorySingleInstance class-level state is clean per test."""
    MemorySingleInstance._held.clear()
    yield
    MemorySingleInstance._held.clear()


def test_default_mutex_name_is_user_scoped():
    assert DEFAULT_MUTEX_NAME.startswith("Local\\")


def test_first_acquire_succeeds():
    a = MemorySingleInstance()
    assert a.acquire() is True


def test_second_acquire_fails_until_release():
    a = MemorySingleInstance()
    b = MemorySingleInstance()
    assert a.acquire() is True
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True


def test_release_idempotent_when_not_held():
    a = MemorySingleInstance()
    a.release()  # never acquired — must not raise


def test_distinct_names_dont_collide():
    a = MemorySingleInstance("Local\\AppA")
    b = MemorySingleInstance("Local\\AppB")
    assert a.acquire() is True
    assert b.acquire() is True


def test_release_only_releases_own_lock():
    a = MemorySingleInstance()
    b = MemorySingleInstance()
    a.acquire()
    b.release()  # b never acquired — must not steal a's lock
    assert b.acquire() is False  # a still holds


def test_best_available_returns_a_guard():
    impl = best_available("Local\\TestApp")
    assert hasattr(impl, "acquire")
    assert hasattr(impl, "release")
