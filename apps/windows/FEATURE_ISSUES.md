# Feature Issues Backlog

This file expands `FEATURE_GAP_ANALYSIS.md` into local, subagent-ready issues.
Each issue is written so it can become a GitHub issue later, but remains usable
as a local task brief.

Baseline validation for every issue:

```powershell
.\scripts\check.ps1
.\build-windows-exe.bat
```

For UI work, also run focused Qt tests before the full check:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/windows/tests/test_preferences.py apps/windows/tests/test_preferences_qt.py -q
```

## Issue 1: Add Custom Zone Layout Domain Model and Persistence

Priority: High

Comparable product: Microsoft PowerToys FancyZones

Problem:
The app only supports built-in Rectangle-style fractions. Users cannot define
their own named layouts or reusable zones, which is the largest remaining gap
against FancyZones.

Scope:
- Add a pure `zones` domain model under `apps/windows/windows_rectangle/core/`.
- Represent a zone as a stable id, display-relative rectangle, and optional name.
- Represent a layout as a stable id, display scope, name, ordered zones, and
  metadata needed for future layout switching/import/export.
- Persist layouts in the JSON config store without breaking existing configs.
- Add config migration tests for older schema versions.
- Add validation for invalid, empty, overlapping, or out-of-bounds zones.

Implementation notes:
- Keep the first implementation independent of Win32 and Qt.
- Store zone geometry in normalized coordinates, not physical pixels, so layouts
  survive DPI and monitor resolution changes.
- Prefer `Fraction` or integer basis points over floats if that keeps geometry
  deterministic.
- Extend `Settings` in `ports/config_store.py` and schema handling in
  `adapters/json_config.py`.
- Do not build the editor UI in this issue; this issue creates the model and
  persistence foundation only.

Suggested tests:
- Unit tests for zone validation and normalized-to-work-area conversion.
- JSON round-trip tests for layouts with multiple zones.
- Migration tests proving existing configs load with an empty layout list.
- Tests proving malformed zone data is ignored or rejected with a clear fallback.

Definition of done:
- `Settings` can load, save, and round-trip custom layouts.
- Existing user config files remain compatible.
- Invalid layout data cannot crash startup.
- Zone-to-rectangle conversion is deterministic across common monitor sizes.
- New tests cover model validation, config migration, and JSON persistence.
- `.\scripts\check.ps1` passes.

## Issue 2: Add a Custom Zone Layout Editor Tab

Priority: High

Comparable product: Microsoft PowerToys FancyZones

Depends on: Issue 1

Problem:
Users need a UI to create and edit custom layouts without modifying JSON by
hand.

Scope:
- Add a Preferences tab for custom layouts.
- Support creating, renaming, duplicating, deleting, and reordering layouts.
- Support adding, resizing, moving, renaming, and deleting zones within a layout.
- Provide a monitor/work-area preview that matches the app's snapping coordinate
  system.
- Include save/apply/reset behavior consistent with the existing Preferences UI.

Implementation notes:
- Keep UI state in a small controller object that can be tested without real
  Win32 windows.
- Keep visual editing predictable: use fixed aspect-ratio preview panels and
  stable handles so text and controls do not shift.
- Use existing Qt patterns in `ui/preferences.py`; split into helper modules if
  the file becomes too large.
- Avoid nested cards or decorative UI; this is an operational settings surface.

Suggested tests:
- Controller-level tests for create/rename/delete/duplicate operations.
- Qt tests for tab visibility, dirty state, save/apply behavior, and validation
  messages.
- Tests for keyboard-accessible editing paths where feasible.
- Screenshot/manual smoke checklist documented if fully automated visual testing
  is not practical in the current harness.

Definition of done:
- A user can create and persist a custom layout entirely through the UI.
- UI prevents saving invalid layouts and explains the blocking problem.
- Existing Preferences shortcuts/settings behavior is not regressed.
- Layout editor has focused unit and Qt tests.
- `.\scripts\check.ps1` passes.

## Issue 3: Apply Active Window to a Single Custom Zone

Priority: High

Comparable product: Microsoft PowerToys FancyZones

Depends on: Issues 1 and 2

Problem:
Custom layouts are only useful when a user can snap the active window into a
selected zone.

Scope:
- Add actions for applying the active window to zones in the active layout.
- Support at least the first nine zones with bindable shortcut actions.
- Add UI rows for these actions in the shortcut editor.
- Use the active monitor's work area and current layout when calculating target
  rectangles.
- Keep history/restore behavior consistent with existing geometry actions.

Implementation notes:
- Add explicit `Action` values only if the current shortcut registry requires
  concrete action identifiers.
- If zone actions need parameters, introduce a small action request type rather
  than overloading string parsing.
- Ensure zone actions use the same eligibility, gap, history, and maximized
  window handling as built-in geometry moves.

Suggested tests:
- Dispatcher tests for applying zone 1, middle zones, and last zone.
- Tests for missing active layout, missing zone index, ineligible window, and
  no-active-window behavior.
- Preferences validation tests for shortcut conflicts with zone actions.
- JSON config tests for persisting custom zone shortcuts.

Definition of done:
- Users can bind shortcuts to custom zone actions.
- The active window moves to the selected zone correctly.
- Restore returns the window to its previous position.
- Missing layout/zone states fail gracefully.
- Focused dispatcher, action, preferences, and config tests are added.
- `.\scripts\check.ps1` passes.

## Issue 4: Snap to Multiple Adjacent Zones

Priority: High

Comparable product: Microsoft PowerToys FancyZones

Depends on: Issues 1 and 3

Problem:
FancyZones allows windows to span multiple adjacent zones. The current app can
only target one fixed rectangle at a time.

Scope:
- Represent a selected zone span as a validated set of adjacent zone ids.
- Compute the union rectangle for a valid zone span.
- Add keyboard support for common spans or a simple selection state.
- Add mouse support only if it can reuse the existing drag session cleanly.
- Persist any user-facing bindings or defaults needed for multi-zone snapping.

Implementation notes:
- Reject non-adjacent or disconnected zone sets in the pure model.
- Keep geometry union logic independent from UI.
- Prefer a minimal first version: contiguous rectangular spans are enough.
- Document limitations clearly if irregular/non-rectangular spans are deferred.

Suggested tests:
- Unit tests for adjacent and non-adjacent zone validation.
- Geometry tests for union rectangle calculation.
- Dispatcher tests for snapping to a valid span.
- UI tests for any exposed controls or shortcut rows.

Definition of done:
- A window can snap to a validated multi-zone span.
- Non-adjacent selections are rejected before dispatch.
- Span geometry is deterministic and gap-aware.
- User-facing controls and shortcuts persist correctly if added.
- `.\scripts\check.ps1` passes.

## Issue 5: Add Quick Layout Switching

Priority: Medium

Comparable product: Microsoft PowerToys FancyZones

Depends on: Issue 1

Problem:
Users with multiple zone layouts need fast switching without opening
Preferences.

Scope:
- Add an active layout concept to settings/runtime state.
- Add bindable actions for next layout, previous layout, and direct selection of
  numbered layouts.
- Add tray menu entries for active layout selection.
- Show the active layout in Preferences and keep it synchronized after save.
- Persist the selected layout across restarts.

Implementation notes:
- Keep layout ids stable; do not use list index as the persisted identity.
- Direct numbered actions can resolve against current display order at runtime.
- Be explicit about behavior when no layouts exist.

Suggested tests:
- Config tests for persisted active layout id.
- Dispatcher or app-context tests for switching actions.
- Tray tests for menu entries and checked active layout state.
- Preferences tests for changing active layout.

Definition of done:
- Users can switch layouts by shortcut and tray menu.
- Active layout persists across restarts.
- Direct selection actions handle missing indexes gracefully.
- All new actions are editable in the shortcut UI.
- `.\scripts\check.ps1` passes.

## Issue 6: Add Snap Assist Chooser for Filling Remaining Space

Priority: Medium

Comparable product: Windows 11 Snap Layouts

Problem:
Windows Snap can offer candidate windows to fill remaining space after a snap.
This app currently only moves the active window.

Scope:
- Enumerate eligible visible top-level windows after a snap action.
- Compute remaining work-area regions created by the snapped active window.
- Present a lightweight chooser UI for selecting another window to fill a
  remaining region.
- Move the selected candidate into the chosen region.
- Add a setting to enable/disable Snap Assist.

Implementation notes:
- Reuse `eligibility.py` so tool windows, hidden windows, and non-resizable
  windows are handled consistently.
- Keep the chooser non-blocking and dismissible with Escape/click-away.
- Avoid stealing focus unnecessarily.
- Start with one remaining region; support multiple regions only if the model is
  clean.

Suggested tests:
- Pure tests for remaining-region calculation.
- Window ranking/filtering tests with fake windows.
- Qt tests for chooser creation, candidate rendering, and selection callback.
- Dispatcher/app integration tests for disabled setting and no-candidate case.

Definition of done:
- When enabled, snap assist appears after supported snap actions with eligible
  candidate windows.
- Selecting a candidate moves it into the remaining region.
- Escape or dismiss leaves windows unchanged.
- The feature can be disabled in Preferences.
- `.\scripts\check.ps1` passes.

## Issue 7: Add Snap Groups

Priority: Medium

Comparable product: Windows 11 Snap Layouts

Depends on: Issue 6

Problem:
Windows Snap can remember grouped windows and restore them together. The app has
single-window history only.

Scope:
- Track groups of windows placed together by Snap Assist or zone operations.
- Add commands to restore, move, or reapply a group where feasible.
- Expose group actions in the tray and/or shortcut editor.
- Prune stale group entries when windows close.

Implementation notes:
- Build on the existing `History` and stale-state pruning patterns.
- Store handles only in runtime state; avoid persisting raw Win32 handles.
- Define explicit behavior for partial groups when some windows are gone.

Suggested tests:
- Unit tests for group create, update, prune, and restore behavior.
- Dispatcher/app tests for group actions with fake windows.
- Tests for partial group failure modes.
- Tray/preferences tests for any exposed controls.

Definition of done:
- The app can remember a group created during a multi-window snap flow.
- Group restore handles closed/missing windows safely.
- Runtime state is pruned to avoid unbounded growth.
- User-facing group commands are discoverable.
- `.\scripts\check.ps1` passes.

## Issue 8: Add Adjacent-Window Resizing

Priority: Medium

Comparable product: Windows 11 Snap Layouts, AquaSnap

Problem:
When two snapped windows share an edge, resizing one should optionally resize
the neighboring window to preserve the layout.

Scope:
- Detect windows adjacent to the active window along a shared edge.
- Add an optional setting for adjacent-window resizing.
- When the active window edge changes, resize the matching neighbor in the
  opposite direction.
- Keep minimum window size and monitor work-area bounds respected.

Implementation notes:
- Put adjacency detection in pure core code using `Rect`.
- Use a tolerance value for off-by-one borders and DPI rounding.
- Do not couple this directly to custom zones; it should work for built-in
  snapped windows too.
- Be conservative with elevated/ineligible windows: skip blocked neighbors.

Suggested tests:
- Geometry tests for shared-edge detection and tolerance.
- Resize-pair tests for left/right/top/bottom edges.
- Dispatcher or app tests with fake windows and blocked neighbors.
- Settings and Preferences tests for the enable/disable control.

Definition of done:
- Adjacent eligible windows resize together when the feature is enabled.
- Blocked or ineligible neighbors are skipped without breaking the active resize.
- Minimum sizes and monitor bounds are respected.
- The feature is disabled by default unless product direction says otherwise.
- `.\scripts\check.ps1` passes.

## Issue 9: Add Magnetic Alignment During Drag

Priority: Medium

Comparable product: AquaSnap

Problem:
Dragging a window near another window's edge should optionally align it to that
edge, not only to monitor edges.

Scope:
- Enumerate nearby eligible windows during drag.
- Detect proximity between moving-window edges and other-window edges.
- Show a preview for the magnetic target.
- Apply the aligned position on drag release.
- Add settings for enable/disable and snap distance.

Implementation notes:
- Reuse existing drag detector/session and overlay code where possible.
- Keep candidate enumeration throttled to avoid UI lag while dragging.
- Avoid aligning to the dragged window itself.
- Respect monitor boundaries and existing gap settings.

Suggested tests:
- Pure geometry tests for edge proximity and target calculation.
- Drag session tests using fake candidate windows.
- Overlay tests for preview state selection.
- Performance-oriented tests proving candidate refresh is throttled.

Definition of done:
- Dragging near another eligible window edge produces a predictable preview.
- Releasing the drag aligns the window as previewed.
- Feature can be configured or disabled.
- Drag performance remains smooth under multiple visible windows.
- `.\scripts\check.ps1` passes.

## Issue 10: Move Adjacent Window Groups Together

Priority: Low

Comparable product: AquaSnap

Depends on: Issue 8

Problem:
AquaSnap can move adjacent window groups together. The current app only moves
the active window.

Scope:
- Identify a connected group of adjacent windows.
- Move all windows in the group by the same delta when the active window is
  moved through supported app actions.
- Keep group movement inside monitor work-area bounds.
- Add a setting to enable/disable group movement.

Implementation notes:
- Build connected-component grouping on top of the adjacency model from Issue 8.
- Start with keyboard/app-triggered movement before supporting arbitrary mouse
  drags.
- Define behavior when only part of the group can move because of bounds or
  blocked windows.

Suggested tests:
- Group detection tests for simple and complex adjacent arrangements.
- Delta clamping tests at monitor edges.
- Dispatcher/app tests with one blocked member.
- Settings/Preferences tests for the feature toggle.

Definition of done:
- Adjacent windows can be grouped and moved together by supported actions.
- Movement is bounded by the destination work area.
- Blocked windows do not corrupt the rest of the group state.
- The behavior is optional and documented.
- `.\scripts\check.ps1` passes.

## Issue 11: Add Mouse Titlebar Shortcuts

Priority: Low

Comparable product: AquaSnap

Problem:
AquaSnap supports mouse shortcuts from titlebar interactions. This app currently
focuses on keyboard shortcuts and edge dragging.

Scope:
- Detect supported titlebar mouse gestures on eligible top-level windows.
- Add bindable mouse actions for common gestures, such as middle-click titlebar
  to toggle always-on-top or double-click variants.
- Add Preferences controls for enabling/disabling and assigning titlebar
  shortcuts.
- Ensure normal window dragging, resizing, and standard titlebar buttons are not
  interfered with.

Implementation notes:
- Prefer Win32 non-client hit testing if reliable; otherwise extend the existing
  mouse hook carefully.
- Keep gesture recognition conservative to avoid accidental activation.
- Document limitations for UWP/elevated windows.
- Do not ship broad low-level mouse behavior without focused tests and manual
  smoke coverage.

Suggested tests:
- Pure gesture recognizer tests for click count, button, modifiers, and timing.
- Adapter tests around hit-test result handling where it can be faked.
- Preferences tests for enabling/disabling gesture bindings.
- Manual smoke checklist for titlebar buttons, dragging, and resizing.

Definition of done:
- At least one titlebar gesture can be bound to an app action.
- Standard titlebar behavior remains unaffected in normal use.
- Gesture settings persist and can be disabled.
- Tests cover recognizer behavior and settings persistence.
- `.\scripts\check.ps1` passes.

## Suggested Implementation Order

1. Issue 1: Add Custom Zone Layout Domain Model and Persistence
2. Issue 2: Add a Custom Zone Layout Editor Tab
3. Issue 3: Apply Active Window to a Single Custom Zone
4. Issue 5: Add Quick Layout Switching
5. Issue 4: Snap to Multiple Adjacent Zones
6. Issue 6: Add Snap Assist Chooser for Filling Remaining Space
7. Issue 7: Add Snap Groups
8. Issue 8: Add Adjacent-Window Resizing
9. Issue 9: Add Magnetic Alignment During Drag
10. Issue 10: Move Adjacent Window Groups Together
11. Issue 11: Add Mouse Titlebar Shortcuts

