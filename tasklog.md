# Windows Rectangle Task Log

Last updated: 2026-08-29

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
- [ ] Reconcile Rectangle feature-parity inventory against the vendored upstream source.
- [x] Implement the pure named-workspace model: layered process/title/regex matching, normalized capture/restore geometry, deterministic multi-monitor planning, and duplicate-window prevention.
- [x] Add schema-v2 workspace persistence, schema-v1 migration, active-workspace validation, and malformed-entry recovery.
- [ ] Wire workspace capture/apply to Win32 enumeration, shortcuts, and the editor UI.
- [x] Wire workspace capture/apply to Win32 visible-window enumeration and return per-placement moved/not-found/blocked results.
- [ ] Wire workspace capture/apply to shortcuts, tray actions, editor UI, and a restore-status overlay.
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
- Research DOCX structural QA: valid archive, 89 paragraphs, 20 headings, one table, and 10 external hyperlinks. Visual rendering was unavailable.
- Updated subprocess and PyInstaller-spec tests for the new `apps/windows` package location.
- Updated the PyInstaller entry point and search path for the monorepo layout.

## Next iteration

Build the capture/review workspace editor, bind workspace shortcuts and tray actions, and add a compact per-window restore result overlay.
