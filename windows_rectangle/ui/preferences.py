"""Preferences staging + validation (brief §2 #15).

The PySide6 widget hasn't been written yet; this module is the
pure-Python service it will sit on top of. Splitting it out means we
can unit-test every interaction the prefs UI cares about — staging a
gap change, rebinding a shortcut, seeing a duplicate-binding warning —
without spinning up Qt.

Lifecycle the UI is expected to use:
    pc = PrefsController(baseline=current_settings)
    pc.set_gap(12)
    pc.set_shortcut(Action.LEFT_HALF, "ctrl+alt+left")
    if pc.is_dirty:
        report = pc.validate()
        if not report.errors:
            pc.commit(on_save=cs.save, on_apply=ctx.apply_settings)

`commit` does NOT touch the OS itself — the caller wires the save/apply
callbacks. This keeps the controller importable without any adapters.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

from ..core.actions import Action
from ..core.shortcuts import (
    ShortcutParseError,
    conflicts as shortcut_conflicts,
    is_reserved,
    normalise as normalise_combo,
)
from ..ports.config_store import Settings


# Gap is a single int in physical pixels. Negative gaps make no sense;
# very large gaps just look silly — clamp at 256 (≈¼ of a 1080p height).
GAP_MIN = 0
GAP_MAX = 256

# almost_maximize_scale lives in (0, 1]. 0.85 is the brief default.
ALMOST_MAX_MIN = 0.1
ALMOST_MAX_MAX = 1.0

# cycle_idle_timeout in seconds: 0 disables cycling (every press is a
# fresh dispatch), small values feel snappy, large values surprise users.
CYCLE_TIMEOUT_MIN = 0.0
CYCLE_TIMEOUT_MAX = 10.0


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Result of `PrefsController.validate()`.

    `errors` are blocking — the UI must prevent commit.
    `warnings` are advisory — the UI shows them but allows commit (e.g.
    "this combo clashes with Windows Snap").
    """

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(slots=True)
class PrefsController:
    """Staged-edits service over a Settings dataclass.

    Holds two copies: the `baseline` (the committed-on-disk snapshot)
    and `staged` (the user's in-flight edits). `is_dirty` compares them.
    """

    baseline: Settings
    staged: Settings = field(init=False)

    def __post_init__(self) -> None:
        self.staged = self._snapshot(self.baseline)

    # ----- staging mutators -------------------------------------------

    def set_gap(self, gap: int) -> None:
        if not isinstance(gap, int) or isinstance(gap, bool):
            raise TypeError("gap must be int")
        self.staged.gap = max(GAP_MIN, min(GAP_MAX, gap))

    def set_launch_at_login(self, enabled: bool) -> None:
        self.staged.launch_at_login = bool(enabled)

    def set_drag_to_edge_enabled(self, enabled: bool) -> None:
        self.staged.drag_to_edge_enabled = bool(enabled)

    def set_almost_maximize_scale(self, scale: float) -> None:
        # Clamp instead of raise — the UI slider can land just outside.
        self.staged.almost_maximize_scale = max(
            ALMOST_MAX_MIN, min(ALMOST_MAX_MAX, float(scale))
        )

    def set_cycle_idle_timeout(self, seconds: float) -> None:
        self.staged.cycle_idle_timeout = max(
            CYCLE_TIMEOUT_MIN, min(CYCLE_TIMEOUT_MAX, float(seconds))
        )

    def set_shortcut(self, action: Action, combo: str) -> None:
        """Stage a shortcut rebind. Raises `ShortcutParseError` if the
        combo is unparseable — UI calls this from a try/except to show
        an inline error without committing.
        """
        # Parse for side-effect (validation); we store the *normalised* form
        # so duplicate detection later doesn't depend on whitespace/case.
        canonical = normalise_combo(combo)
        self.staged.shortcuts[action] = canonical

    def clear_shortcut(self, action: Action) -> None:
        """Remove a shortcut binding. Cleared shortcuts won't register."""
        self.staged.shortcuts.pop(action, None)

    # ----- inspection -------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        return self.staged != self.baseline

    def shortcut_conflicts(self) -> dict[Action, list[Action]]:
        """Group actions whose canonical combo collides with another.

        Maps `winner_action -> [other_action, ...]` — the first action
        wins the slot, the rest are flagged duplicates. Used by the UI
        to render red strikethroughs in the table.
        """
        # `core.shortcuts.conflicts` works on a {name: combo} mapping;
        # we adapt our Action keys to/from strings for that call.
        as_strings = {a.value: c for a, c in self.staged.shortcuts.items()}
        raw = shortcut_conflicts(as_strings)
        out: dict[Action, list[Action]] = {}
        for winner_str, dupes in raw.items():
            winner = Action(winner_str)
            out[winner] = [Action(d) for d in dupes]
        return out

    def reserved_bindings(self) -> list[tuple[Action, str]]:
        """List staged shortcuts that step on an OS-reserved combo."""
        return [
            (action, combo)
            for action, combo in self.staged.shortcuts.items()
            if is_reserved(combo)
        ]

    def validate(self) -> ValidationReport:
        """Compute a fresh report against the current `staged` state."""
        errors: list[str] = []
        warnings: list[str] = []

        # Range sanity (clamped on set, but a direct .staged mutation
        # could bypass — guard anyway).
        if not (GAP_MIN <= self.staged.gap <= GAP_MAX):
            errors.append(f"gap {self.staged.gap} out of range [{GAP_MIN}, {GAP_MAX}]")
        if not (ALMOST_MAX_MIN <= self.staged.almost_maximize_scale <= ALMOST_MAX_MAX):
            errors.append(
                f"almost_maximize_scale {self.staged.almost_maximize_scale} "
                f"out of range [{ALMOST_MAX_MIN}, {ALMOST_MAX_MAX}]"
            )
        if not (CYCLE_TIMEOUT_MIN <= self.staged.cycle_idle_timeout <= CYCLE_TIMEOUT_MAX):
            errors.append(
                f"cycle_idle_timeout {self.staged.cycle_idle_timeout} "
                f"out of range [{CYCLE_TIMEOUT_MIN}, {CYCLE_TIMEOUT_MAX}]"
            )

        # Shortcut sanity — parse failures become errors, conflicts/reserved
        # become warnings (the user might want to keep a power-user combo).
        for action, combo in self.staged.shortcuts.items():
            try:
                normalise_combo(combo)
            except ShortcutParseError as e:
                errors.append(f"{action.value}: cannot parse {combo!r}: {e}")

        dupes = self.shortcut_conflicts()
        for winner, others in dupes.items():
            for other in others:
                warnings.append(
                    f"{other.value} shares combo with {winner.value} — only one will fire"
                )

        for action, combo in self.reserved_bindings():
            warnings.append(
                f"{action.value}: {combo} clashes with an OS-reserved shortcut"
            )

        return ValidationReport(tuple(errors), tuple(warnings))

    # ----- commit / revert --------------------------------------------

    def commit(
        self,
        on_save: Callable[[Settings], None] | None = None,
        on_apply: Callable[[Settings], None] | None = None,
    ) -> ValidationReport:
        """Validate and, if clean, persist + apply the staged settings.

        - `on_save(settings)` typically wraps `ConfigStore.save`.
        - `on_apply(settings)` typically wraps `AppContext.apply_settings`.

        Returns the ValidationReport. If `report.ok` is False, neither
        callback fires and the baseline is untouched.
        """
        report = self.validate()
        if not report.ok:
            return report
        if on_save is not None:
            on_save(self.staged)
        if on_apply is not None:
            on_apply(self.staged)
        # Promote staged → baseline; copy so further edits don't mutate
        # what we just handed to the callbacks.
        self.baseline = self._snapshot(self.staged)
        self.staged = self._snapshot(self.baseline)
        return report

    def revert(self) -> None:
        """Throw away staged changes and start fresh from baseline."""
        self.staged = self._snapshot(self.baseline)

    # ----- internals --------------------------------------------------

    @staticmethod
    def _snapshot(settings: Settings) -> Settings:
        """Deep-copy Settings so mutable fields (`shortcuts` dict) are
        independent between staged and baseline."""
        return copy.deepcopy(settings)
