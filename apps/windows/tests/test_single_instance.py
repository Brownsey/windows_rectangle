"""Tests for windows_rectangle.adapters.single_instance."""

import sys
import uuid

import pytest

from windows_rectangle.adapters.single_instance import (
    MemorySingleInstance,
    WindowsMutexSingleInstance,
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


@pytest.mark.skipif(sys.platform != "win32", reason="win32 only")
def test_windows_mutex_closes_duplicate_and_owner_handles():
    name = f"Local\\WindowsRectangleTest-{uuid.uuid4()}"
    owner = WindowsMutexSingleInstance(name)
    duplicate = WindowsMutexSingleInstance(name)
    replacement = WindowsMutexSingleInstance(name)
    try:
        assert owner.acquire() is True
        assert duplicate.acquire() is False
        owner.release()
        assert replacement.acquire() is True
    finally:
        owner.release()
        duplicate.release()
        replacement.release()
