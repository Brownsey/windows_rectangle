# Windows Rectangle Task Log

Last updated: 2026-09-02

## Current objective

Build a polished Windows counterpart to Rectangle with robust keyboard and drag snapping, multi-monitor support, customizable named-window layouts, and excellent usability and performance.

## Completed before this iteration

- Core snap geometry, keyboard dispatch, drag detection, overlay previews, undo history, cycling, monitor selection, borders, cleanup, autostart, single-instance handling, and Win32 adapters.
- Preferences, tray UI, shortcut rebinding and conflict reporting, pause/reset controls, diagnostics, log handling, import/export, packaging scripts, and Windows build documentation.
- Vendored upstream Rectangle snapshot and reorganized the repository into platform-specific apps.

## 2026-08-29 — Active iteration

- [x] Audited repository structure, history, tests, and merge state.
- [x] Identified an interrupted merge between 64 newer local Windows commits and the remote monorepo reorganization.
- [x] Resolved content conflicts by retaining the newer Windows implementation/tests at `apps/windows` paths, the monorepo README, and both platforms' ignore rules.
- [x] Verify the reorganized app with lint, type checks, and tests.
- [x] Reconcile Rectangle feature-parity inventory against the vendored upstream source; priorities and acceptance criteria are recorded in `research/rectangle-parity-audit.md`.
- [x] Implement the pure named-workspace model: layered process/title/regex matching, normalized capture/restore geometry, deterministic multi-monitor planning, and duplicate-window prevention.
- [x] Add schema-v2 workspace persistence, schema-v1 migration, active-workspace validation, and malformed-entry recovery.
- [x] Wire workspace capture/apply to Win32 enumeration, shortcuts, and the editor UI.
- [x] Wire workspace capture/apply to Win32 visible-window enumeration and return per-placement moved/not-found/blocked results.
- [x] Register per-workspace global shortcuts using a bounded main-thread dispatch queue, with binding failures shown alongside action-shortcut status.
- [x] Add tray capture, manage, and restore actions with compact moved/not-found/blocked status feedback.
- [x] Add a staged workspace editor for capture, rename, shortcut assignment, process/title/regex matching, monitor targeting, rule deletion, match testing, validation, save, and immediate restore.
- [x] Exclude Windows Rectangle's own editor windows from workspace capture.
- [x] Restore the advertised corner-sixth actions, maximize-width, and always-on-top toggle across geometry, Win32, shortcuts, configuration, and UI labels.
- [x] Add 17 advanced P0 actions using reusable orientation-aware band, edge-move, and dimension-resize primitives: fourths, three-fourths, centered spans, directional moves, and width/height-only resizing.
- [x] Keep advanced actions discoverable but unbound by default to avoid shortcut overload.
- [x] Finish P0 parity with anchored halve/double sizing, prominent centering, and direct display 1–9 commands with unavailable-display feedback.
- [x] Add a reusable integer-grid tile primitive and use it for complete sixths, orientation-aware quadrant thirds, and vertical thirds/two-thirds.
- [x] Allow custom setups to be authored while applications are closed: empty workspaces, manual process/title rules, monitor selection, and reusable named position presets.
- [x] Add workspace UI actions for creating an empty setup, adding an application, and changing a rule's position without recapturing.
- [x] Add a visual monitor canvas with labeled application cards, synchronized table selection, drag-to-position, edge clamping, and normalized grid snapping.
- [x] Add an Office template (Slack top-left, Outlook bottom-left, Chrome right-half) and a RuneScape wizard that creates title-specific account rules in a balanced grid.
- [x] Add per-rule match status, workspace duplication, unsaved-change Save/Discard/Cancel handling, clearer workspace guidance, and end-user documentation.
- [x] Make the visual editor genuinely freeform: basis-point-precision movement, draggable edge/corner resizing, visible handles, minimum sizes, and monitor-bound clamping.
- [x] Add “Record current positions” to learn exact live window rectangles and monitor assignments while preserving saved geometry for unmatched applications.
- [x] Autosave and immediately apply every valid workspace edit; retain dirty state and surface errors when validation, persistence, or runtime application fails.
- [x] Replace the redundant Apply/Save workflow with automatic saving, a manual retry action, and a single Done action.
- [x] Conduct Deep Research on comparable Windows managers and synthesize actionable UX/performance guidance.
- [x] Generate `research/Windows-Rectangle-UX-Research.docx` with first-party citations and a prioritized roadmap.

## Product principles

- Fast default workflow; advanced configuration remains discoverable but unobtrusive.
- Safe, previewable actions with clear recovery (undo, conflict feedback, diagnostics).
- Stable matching across restarts using layered identity signals rather than title-only matching.
- Per-monitor-DPI correctness and minimal work on hook/hotkey threads.

## Verification record

- `scripts/check.ps1`: passed Ruff lint, Ruff format, and strict mypy for the pure core.
- Pytest: 517 passed, 16 skipped (the skipped tests require optional PySide6, which is not installed in the current environment).
- After workspace foundation: 530 passed, 16 skipped.
- After Win32 workspace capture/apply: 534 passed, 16 skipped, including Windows-only enumeration smoke coverage.
- After end-to-end workspace UX: 544 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After the first parity restoration pass: 554 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After reusable P0 layouts and movement: 573 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After completing the P0 action catalogue: 585 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After the first reusable dense-grid pass: 596 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After manual custom-setup authoring: 602 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After visual workspace editing: 605 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After templates and workspace UX polish: 609 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed. Optional Qt installation was attempted but the package mirror did not complete, so rendered Qt tests remain skipped.
- After freeform canvas resizing: 612 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After exact live-position recording: 615 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- After reliable workspace autosave: 618 passed, 16 skipped; Ruff, Ruff format, and strict mypy all passed.
- Research DOCX structural QA: valid archive, 89 paragraphs, 20 headings, one table, and 10 external hyperlinks. Visual rendering was unavailable.
- Updated subprocess and PyInstaller-spec tests for the new `apps/windows` package location.
- Updated the PyInstaller entry point and search path for the monorepo layout.

## Next iteration

Add per-monitor canvas filtering and integrate Workspaces into the primary Preferences navigation before continuing dense-grid parity.
