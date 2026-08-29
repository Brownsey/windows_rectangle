# Windows Rectangle: UX and Product Research

Audience: product owner and implementers  
Date: 29 August 2026  
Scope: Windows 11-first window management, with Windows 10 compatibility where practical; Rectangle parity plus differentiated named multi-window workspaces.

## Executive answer

The product should remain a fast, lightweight Rectangle-style snapper at its core, then differentiate with a capture-first named workspace workflow. A user should arrange windows once, choose **Save workspace**, review automatically detected app/account matches, assign an optional shortcut, and later restore the arrangement with one action. Restore must be transparent: preview what will move, show per-window success or failure, never assign one window twice, and explain elevated/unmatched windows.

The current schema-v2 workspace foundation is directionally correct. It already uses the two strongest identity signals—process name and title criteria—and normalized monitor-relative geometry. The next implementation should prioritize Win32 enumeration/apply, capture and review UI, restore status, and atomic multi-window movement before adding app launching or complex automation.

## What comparable products establish

### Capture first, then edit

PowerToys Workspaces lets users arrange a live desktop, capture it, then name and adjust the result. During launch it shows per-app pending, successful, and failed states and permits cancellation. This is the clearest low-friction model for the requested RuneScape and office examples. [PowerToys Workspaces](https://learn.microsoft.com/en-us/windows/powertoys/workspaces)

Rectangle Pro similarly offers **Save Current Layout**, captures one or all displays, and converts known positions to semantic presets when possible. It supports keyboard shortcuts, display-based triggers, and per-entry matching. [Rectangle Pro Layouts](https://rectangleapp.com/pro/docs/layouts/)

Recommendation: make **Capture current windows…** the primary creation path and **New empty workspace** secondary. After capture, open a review screen rather than saving silently.

### Matching needs layers and visible confidence

MaxTo identifies windows by process name, class, and title, and says process plus title is the sensible default in most cases. It supports wildcards and regex for harder cases. DisplayFusion also uses process filename, window class, and window text, while warning that identical rules are ambiguous. Rectangle Pro provides Any, loose, substring, and regex title modes and applies one-to-one matching unless the user explicitly requests all matches. [MaxTo window matching](https://docs.maxto.net/how-to/find-window/), [DisplayFusion Window Position Profiles](https://www.displayfusion.com/HelpGuide/WindowPositionProfiles/), [Rectangle Pro Layouts](https://rectangleapp.com/pro/docs/layouts/)

Recommendation: default captured entries to exact process plus a suggested title substring; label the resulting confidence as **Strong**, **Broad**, or **Ambiguous**. Keep regex under an Advanced disclosure. Add window class later as a fallback, not as the primary UI.

### Layout geometry must survive monitor changes

FancyZones uses relative grid layouts that resize across screen sizes, supports separate defaults for horizontal and vertical monitors, keeps windows in their zones after resolution changes, and can move windows when a layout changes. Rectangle Pro accepts fractional screen dimensions and display identifiers. [FancyZones](https://learn.microsoft.com/en-us/windows/powertoys/fancyzones), [Rectangle Pro Layouts](https://rectangleapp.com/pro/docs/layouts/)

Recommendation: keep the implemented 0–10,000 normalized coordinate model. Add a stable monitor fingerprint (device identifier plus last-known bounds/DPI) and a clear fallback policy: exact monitor, equivalent orientation, primary monitor. Preview remapping when the saved topology is absent.

### Fast activation needs feedback

FancyZones supports numbered quick-switch hotkeys and flashes zones when switching. DisplayFusion loads profiles from settings, tray, title-bar button, hotkey, command line, monitor-profile changes, or triggers. Rectangle exposes a URL action API; Rectangle Pro layouts can run from shortcuts and menus. [FancyZones](https://learn.microsoft.com/en-us/windows/powertoys/fancyzones), [DisplayFusion Window Position Profiles](https://www.displayfusion.com/HelpGuide/WindowPositionProfiles/), [Rectangle README](https://github.com/rxhanson/Rectangle)

Recommendation: support three activation paths in the first release—global shortcut, tray menu, and CLI. Show a subtle 600–900 ms overlay naming the workspace and summarizing “3 moved · 1 not found”; clicking it should open details.

### Windows-native assist patterns reduce cognitive load

Windows Snap Assist shows remaining windows after the first snap, while Snap groups let users return to a window set through Task View, Alt+Tab, or taskbar affordances. FancyZones provides visual zone previews, zone numbers, multiple-zone selection, and fully keyboard-operable grid/canvas editors. [Windows Snap](https://support.microsoft.com/en-us/windows/experience/snap-your-windows), [FancyZones](https://learn.microsoft.com/en-us/windows/powertoys/fancyzones)

Recommendation: after a partial workspace restore, offer unmatched candidate windows as a compact picker. The workspace editor must be operable by keyboard, with labeled focus order, arrow-key nudging, and a live footprint preview.

### Performance and security constraints should be visible, not mysterious

FancyZones notes that displaying zones on every monitor during dragging can affect performance and documents DPI/application compatibility limits. Microsoft explains that moving elevated windows can require elevation, but recommends against always running elevated. PowerToys Workspaces cannot place a window before its app launches and therefore exposes launch progress. [FancyZones](https://learn.microsoft.com/en-us/windows/powertoys/fancyzones), [PowerToys administrator mode](https://learn.microsoft.com/en-us/windows/powertoys/administrator), [PowerToys Workspaces](https://learn.microsoft.com/en-us/windows/powertoys/workspaces)

Recommendation: enumerate only on capture/restore and event-triggered refresh, cache immutable metadata briefly, and keep mouse-hook work constant-time. Do not request permanent elevation by default. Detect access-denied moves and show **Needs administrator access** with a one-time restart option.

For smoother restores, use `BeginDeferWindowPos`/`DeferWindowPos`/`EndDeferWindowPos`: Microsoft documents these APIs for changing several windows together, including position, size, z-order, and show state. This should reduce intermediate repaints and make a workspace appear atomically. [Microsoft Window Features](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features)

## Prioritized roadmap

### P0 — Complete the named workspace workflow

1. Extend the window adapter with visible top-level enumeration and metadata: title, process executable/name, class, minimized/elevated state, and monitor.
2. Capture the current desktop into normalized placements, excluding the app itself, shells, tool windows, cloaked windows, and empty-title windows by default.
3. Apply plans with deferred positioning, restore minimized/maximized windows deliberately, preserve undo history, and return a structured result per placement.
4. Add workspace shortcut registration with the existing conflict detector, plus tray and CLI actions.
5. Add a non-modal progress/result surface: moved, not found, ambiguous, blocked, cancelled.

Success measure: a user can configure Slack top-left, Outlook bottom-left, and Chrome right-half—or multiple named RuneLite accounts—without editing JSON, then restore them reliably after restart.

### P1 — Make setup safe and understandable

1. Capture/review wizard with miniature monitor previews.
2. Live match testing: each rule shows the currently matched window(s).
3. Confidence warnings for title-only or duplicate rules.
4. Duplicate, rename, reorder, export/import, and “Update from current positions.”
5. Monitor-topology fallback preview and per-workspace behavior for missing displays.

### P2 — Reach and exceed Rectangle/FancyZones parity

1. Custom zones with grid and canvas editors, keyboard editing, multi-zone spans, and quick switching.
2. Snap Assist-style picker for filling unassigned zones.
3. Per-app remembered last zone and optional automatic placement when a matching window opens.
4. Adjacent-window resizing and magnetic alignment; AquaSnap demonstrates the value of resizing or moving adjacent groups together. [AquaSnap](https://www.nurgo-software.com/products/aquasnap)
5. URL/CLI action API, workspace desktop shortcuts, and event triggers such as display reconnect or wake.

### P3 — Advanced automation, kept opt-in

1. Launch missing applications with optional arguments and bounded wait/retry.
2. Bring matches to front; optionally minimize non-workspace apps.
3. Rule priority, match-all repetitions, and window-open triggers.
4. Monitor-profile bindings and topology-aware automatic restore.

## UX specification for workspace creation

1. **Capture:** user arranges windows and chooses **Save current workspace…**.
2. **Review:** show monitor thumbnails and one row per detected window with app icon, friendly name, detected process, editable title rule, destination monitor, and footprint.
3. **Validate:** inline warnings explain broad or duplicate matches; **Test matches** highlights matched live windows without moving them.
4. **Activate:** user names the workspace and optionally records a shortcut. Shortcut conflicts are shown before save.
5. **Restore:** a compact overlay displays progress and can cancel outstanding launch/wait work. Completion collapses to a short summary.
6. **Recover:** unmatched or blocked entries stay visible with actions: choose window, edit match, retry as administrator, or ignore this time.

Use progressive disclosure. Most users should see **App**, **Window name contains**, and **Position**. Regex, class, launch command, elevation, match-all, triggers, and missing-app behavior belong under Advanced.

## Performance budget

- Hook callback: no enumeration, regex, disk I/O, or Qt work.
- Idle CPU: effectively zero; prefer WinEvent notifications over polling.
- Workspace planning: under 20 ms for 100 visible windows and 30 placements on ordinary hardware.
- Restore initiation feedback: under 100 ms.
- Position application: one deferred batch where compatible; isolate failures and retry individually only when needed.
- Overlay scope: current/target monitors only by default.
- Config writes: retain atomic write-and-replace; debounce editor autosave or save explicitly.

## Limitations and open decisions

- Elevated windows cannot reliably be manipulated from a non-elevated process; the product should explain this instead of silently failing.
- Titles change frequently in browsers and document editors. Capture suggestions must be editable, and exact-title matching should not be the default for those apps.
- Some applications are single-instance or do not create windows predictably after launch. Application launching should follow reliable move-existing behavior, not block the first workspace release.
- Native Windows Snap group integration is not exposed as a simple public contract in the reviewed documentation. Recreate the useful restore UX without claiming OS Snap-group membership.
- Windows 10 reached end of support on 14 October 2025 according to Microsoft; new UX should target Windows 11 while retaining best-effort Windows 10 execution.

## Research gap matrix

| Claim family | Evidence | Confidence | Remaining gap |
| --- | --- | --- | --- |
| Capture/edit/status workflow | PowerToys Workspaces, Rectangle Pro | High | Exact UI implementation is product-specific |
| Process/title matching | MaxTo, DisplayFusion, Rectangle Pro | High | Add class/UWP identity only after field testing |
| Normalized geometry | FancyZones, Rectangle Pro | High | Stable physical-display identity needs implementation testing |
| Hotkey/tray/CLI activation | FancyZones, DisplayFusion, Rectangle | High | Choose default shortcut after Windows conflict testing |
| Deferred batch movement | Microsoft Win32 docs | High | Benchmark repaint and partial-failure behavior |
| Elevation limitations | Microsoft PowerToys docs | High | Test exact error reporting with representative elevated apps |
| Adjacent group behavior | AquaSnap first-party feature page | Medium | Interaction details and edge cases need prototyping |

## Search record and stop rationale

Discovery covered official documentation for Rectangle/Rectangle Pro, Windows Snap, PowerToys FancyZones and Workspaces, DisplayFusion, MaxTo, AquaSnap, and Win32 positioning/elevation. Follow-up targeted matching semantics, capture/status behavior, keyboard editing, multi-monitor/DPI behavior, performance warnings, and batch positioning. Research stopped because every consequential roadmap claim has first-party support or an explicit limitation; further search was returning duplicative feature descriptions rather than evidence likely to change priorities.

## Claim-to-source ledger

- Microsoft, “Workspaces utility for Windows desktop management,” updated 20 August 2025: capture, editor, launch status, launch limitations, moving existing windows. https://learn.microsoft.com/en-us/windows/powertoys/workspaces
- Microsoft, “FancyZones window manager utility,” updated 30 July 2026: relative layouts, keyboard editor, quick switching, resolution behavior, performance and compatibility. https://learn.microsoft.com/en-us/windows/powertoys/fancyzones
- Microsoft Support, “Snap Your Windows,” accessed 29 August 2026: Snap Assist, layouts, groups, and resizing. https://support.microsoft.com/en-us/windows/experience/snap-your-windows
- Ryan Hanson, “Rectangle” README, accessed 29 August 2026: snap areas, ignore-app behavior, URL action API. https://github.com/rxhanson/Rectangle
- Rectangle Pro, “Layouts,” accessed 29 August 2026: capture, triggers, matching modes, display selection, fractional geometry, preview. https://rectangleapp.com/pro/docs/layouts/
- Binary Fortress, “Window Position Profiles,” accessed 29 August 2026: capture/restore paths, hotkeys, CLI, monitor profiles, match ambiguity. https://www.displayfusion.com/HelpGuide/WindowPositionProfiles/
- MaxTo, “Find any window,” accessed 29 August 2026: process/class/title identity, wildcard and regex matching. https://docs.maxto.net/how-to/find-window/
- Nurgo Software, “AquaSnap,” accessed 29 August 2026: magnetic alignment, adjacent resizing/group movement, shortcuts, performance positioning. https://www.nurgo-software.com/products/aquasnap
- Microsoft, “Window Features,” accessed 29 August 2026: deferred simultaneous multi-window positioning. https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features
- Microsoft, “Run PowerToys in Administrator Mode,” updated 15 April 2026: elevated-window restrictions and secure-by-default guidance. https://learn.microsoft.com/en-us/windows/powertoys/administrator
