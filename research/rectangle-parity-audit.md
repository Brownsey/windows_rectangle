# Rectangle parity audit

Last audited: 2026-08-29

This inventory compares the vendored Rectangle source in `apps/mac/Rectangle` with the
Windows implementation. The authoritative command list is
`Rectangle/WindowAction.swift`; behavior is cross-checked against `WindowCalculation`,
`Snapping`, `MultiWindow`, `TitleBarManager.swift`, and `Defaults.swift`.

## Current coverage

Windows Rectangle now exposes 76 keyboard actions:

- Halves, corner quarters, corner sixths, horizontal thirds, and two-thirds.
- Maximize, maximize height, maximize width, almost maximize, and center.
- Fourths and three-fourths, centered half/two-thirds/three-fourths, with
  orientation-aware behavior on portrait displays.
- Symmetric and width/height-only larger/smaller, edge-aligned movement,
  restore, next/previous display, and always-on-top.
- Anchored halve/double width and height, prominent center, and direct display
  1–9 targeting.
- Complete sixths, orientation-aware quadrant thirds, and vertical thirds/two-thirds.

It also has Windows-native drag-to-edge snapping, previews, gaps, cycling, undo,
multi-monitor movement, shortcut customization, tray controls, diagnostics, and named
multi-window workspace capture/restore. Named workspaces are a deliberate extension
beyond the open-source Rectangle feature set.

## Remaining command parity

### P0 — common daily layout operations

Complete. Advanced P0 commands are discoverable but unbound by default.

### P1 — dense grid layouts

- Complete eighth, ninth, twelfth, and sixteenth grids.
- User-specified rectangle action.

### P1 — multi-window commands

- Tile all and cascade all.
- Tile/cascade windows belonging to the active application.
- Reverse all managed windows.
- To-do left/right modes.

### P2 — platform-specific interaction parity

- Customizable snap-area editor and compound snap areas.
- Cooperative corner resize and adjacent-window resizing.
- Title-bar action gestures.
- Rectangle's execution-mode variants and URL-triggered commands, translated into a
  suitable Windows CLI/protocol surface.

## UX and implementation order

1. Add generic fractional-grid and anchored-resize primitives so the large command
   catalogue does not become a collection of one-off functions.
2. Expose advanced actions as unbound by default, searchable in Preferences. Keep the
   existing compact default shortcut profile.
3. Add a visual custom-zone editor that reuses normalized workspace geometry and shows
   a monitor preview before saving.
4. Add multi-window tiling with deferred/batched Win32 positioning and explicit partial
   failure results.
5. Add direct-monitor actions and a small CLI, then validate hot-plug and DPI behavior.

## Acceptance rule

An item is only marked complete when its core geometry/orchestration tests, config
round-trip, discoverable UI label, runtime adapter path, and full quality gate pass.
