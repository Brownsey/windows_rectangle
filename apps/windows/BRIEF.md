# Windows Rectangle — Project Brief

A Rectangle-for-Windows window manager. Feature-parity clone of the macOS
[Rectangle](https://github.com/rxhanson/Rectangle) app, built in Python and
runnable on Windows 10/11.

> **Iteration log** at bottom. This document converges over multiple passes.

---

## 1. Reality check: can we "copy the Rectangle app"?

No — not as a literal port. Rectangle is:

- **Swift + AppKit**, macOS-only.
- Moves/resizes windows via the macOS **Accessibility API** (`AXUIElement`).
- Registers shortcuts via **Carbon / MASShortcut**.
- Ships as a `.app` bundle with a macOS menu-bar (`NSStatusItem`) UI.

None of that runtime exists on Windows. So "take a copy and make it work"
means: **treat Rectangle as the spec**, replicate its feature set and UX 1:1,
and reimplement each macOS dependency with its Windows equivalent.

What we *can* copy directly from the Rectangle source:

- The **window-geometry math** (halves, thirds, quarters, sixths, center,
  maximize, larger/smaller, gaps). This is plain arithmetic — language-agnostic.
- The **default keyboard shortcut map**.
- The **action catalogue** and naming.

**Licensing:** Rectangle is **MIT-licensed**. Reusing its geometry math,
action catalogue and default shortcut map is permitted with attribution.
Include Rectangle's MIT notice in `THIRD_PARTY_NOTICES`. This Windows app is
a fresh Python implementation; the macOS app is a vendored upstream Rectangle
source snapshot under `apps/mac/Rectangle`.

---

## 2. Feature parity target (from Rectangle free tier)

| # | Action | Default shortcut (macOS → proposed Win) |
|---|--------|------------------------------------------|
| 1 | Left / Right / Top / Bottom half | `Ctrl+Alt+←/→/↑/↓` |
| 2 | Top-Left/-Right, Bottom-Left/-Right quarter | `Ctrl+Alt+U/I/J/K` |
| 3 | Top-left/-right, Bottom-left/-right sixth | `Ctrl+Insert/PgUp/Delete/PgDown` |
| 4 | First / Center / Last third | `Ctrl+Alt+D/F/G` |
| 5 | First / Last two-thirds | `Ctrl+Alt+E/T` |
| 6 | Maximize | `Ctrl+Alt+Enter` |
| 7 | Maximize height / width | `Ctrl+Alt+Shift+↑/→` |
| 8 | Almost maximize (~85%) | `Ctrl+Alt+Shift+Enter` |
| 9 | Center (no resize) | `Ctrl+Alt+C` |
| 10 | Make larger / smaller | `Ctrl+Alt+=` / `Ctrl+Alt+-` |
| 11 | Restore (undo) | `Ctrl+Alt+Backspace` |
| 12 | Move to next / prev display | `Ctrl+Alt+.` / `Ctrl+Alt+,` |
| 13 | Toggle always on top | `Ctrl+Alt+Shift+Space` |
| 14 | Next-third cycle (repeat key cycles) | repeated half/third presses |
| 15 | **Drag-to-edge snapping** (footprint preview) | mouse to screen edge/corner |
| 16 | Configurable **gap** between windows | n/a (setting) |
| 17 | System-tray menu + preferences window | n/a |
| 18 | Launch at login | n/a |

Pro-only / out of scope v1: Stage-manager features, "Todo mode", custom
named layouts, cascade. Park as backlog.

Note - all the shortcuts should be customisable when opening the app. It should be an .exe or quickly that once opened - all shortcuts can be configured. Then when running the app those shortcuts work, when app is closed the features are turned off.

> Note: Windows already ships **Snap** (`Win+←/→`) and PowerToys **FancyZones**.
> Differentiator = Rectangle's exact shortcut ergonomics, thirds/sixths,
> repeat-cycling, undo, and macOS-style edge snapping with gaps.

---

## 3. macOS dependency → Windows equivalent (all Python-implementable)

| Rectangle (macOS) | Windows replacement | Python access |
|-------------------|---------------------|---------------|
| `AXUIElement` move/resize | `SetWindowPos`, `GetWindowRect`, `MoveWindow` (user32) | **pywin32** (`win32gui`) / `ctypes` |
| Frontmost window | `GetForegroundWindow` | `win32gui.GetForegroundWindow()` |
| Screen list + visibleFrame (excludes Dock/menu) | `EnumDisplayMonitors` + `GetMonitorInfo` → `rcWork` (excludes taskbar) | `win32api` |
| Carbon global hotkeys | `RegisterHotKey` + message pump | `ctypes`/`win32gui` |
| Drag-to-edge tracking | Low-level mouse hook `WH_MOUSE_LL` | `ctypes SetWindowsHookEx` |
| `NSStatusItem` menu bar | System tray icon | **PySide6** `QSystemTrayIcon` |
| Preferences window | Native GUI | **PySide6** (Qt) |
| Login item | `HKCU\...\Run` registry key or Startup folder | `winreg` |
| Snap footprint preview | Translucent borderless topmost **click-through, no-activate** overlay (`WS_EX_LAYERED \| WS_EX_TRANSPARENT \| WS_EX_NOACTIVATE`) | frameless Qt widget |
| `UserDefaults` | JSON config in `%APPDATA%` | `json` + `pathlib` |

**Everything above is doable on Windows with pure Python + ctypes/pywin32.**
No C extension we must compile ourselves.

---

## 4. Architecture (hexagonal / ports-and-adapters)

Keep OS calls at the edges so the geometry logic stays pure and testable.

```
windows_rectangle/
├── core/                      # pure, no win32 — unit-testable
│   ├── geometry.py            # Rect, fraction math, gap logic
│   ├── actions.py             # action enum + Rect transforms
│   ├── cycle.py               # repeat-key cycling state
│   └── history.py             # per-window undo stack
├── ports/                     # interfaces (Protocols / ABCs)
│   ├── window_manager.py      # get_active, move_resize, list_monitors
│   ├── hotkeys.py             # register(combo, callback)
│   └── config_store.py
├── adapters/                  # Windows implementations
│   ├── win32_windows.py       # pywin32 SetWindowPos etc.
│   ├── win32_hotkeys.py       # RegisterHotKey + msg loop thread
│   ├── win32_mousehook.py     # WH_MOUSE_LL drag-snap detection
│   ├── win32_overlay.py       # footprint preview window
│   ├── win32_autostart.py     # winreg
│   └── json_config.py
├── ui/
│   ├── tray.py                # QSystemTrayIcon menu
│   └── preferences.py         # PySide6 settings + shortcut recorder
├── app.py                     # composition root: wires ports↔adapters
└── tests/                     # pytest, mocks at the ports
```

`core` imports nothing OS-specific → fast, deterministic unit tests with no
real windows. `app.py` is the only place adapters get bound to ports.

---

## 5. Hard technical problems + chosen solution

1. **Per-monitor DPI scaling** — wrong coords on mixed-DPI/scaled displays.
   → Declare process *Per-Monitor-V2 DPI aware* at startup via
   `SetProcessDpiAwarenessContext(-4)` (ctypes). Compute geometry in physical
   pixels per monitor's `rcWork`.

2. **Windows 10/11 invisible border** — `GetWindowRect` includes an
   ~7px drop-shadow margin; naive placement leaves visible gaps.
   → Correct with `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` and
   offset by the delta when positioning.

3. **Elevated (admin) windows** — a non-admin process cannot move a window
   owned by an elevated process (UIPI).
   → Document the limitation; offer optional "run as admin" build. Fail
   gracefully (no crash) when `SetWindowPos` is blocked.

4. **Maximized / snapped state** — `SetWindowPos` on a maximized window
   misbehaves.
   → Detect via `GetWindowPlacement`; `ShowWindow(SW_RESTORE)` before moving.

5. **Global hotkey conflicts** with OS/other apps — `RegisterHotKey` fails
   silently if a combo is taken.
   → Check return code; surface conflicts in the prefs UI; allow rebinding.

6. **Hotkey message pump** must run on a thread with a message loop.
   → Dedicated daemon thread running `GetMessage` loop; marshal callbacks to
   the action handler thread-safely (queue).

7. **Drag-to-edge without lag** — low-level mouse hook runs in-process and
   must return fast or Windows drops it.
   → Hook only sets a flag/coords; heavy work (which monitor edge, preview)
   done off the hook callback. Throttle.

8. **Competing event loops** — `WH_MOUSE_LL` and `RegisterHotKey` each need a
   thread with a Win32 message loop; Qt has its own `QApplication` loop.
   → **Qt `QApplication` is the single main loop.** Hotkey pump and mouse hook
   each run on their own daemon thread with a private `GetMessage` loop; they
   marshal events back to the Qt thread via `QMetaObject.invokeMethod` /
   a thread-safe queue. Using `QSystemTrayIcon` (not pystray) removes a second
   competing loop and one dependency tree.

9. **Cycle state & undo identity** — repeat-key cycling and per-window undo key
   on the window's `HWND`. HWNDs can be recycled after a window closes.
   → Key history/cycle state by `HWND`; validate with `IsWindow(hwnd)` before
   use and evict stale entries. Cycle state resets after a short idle timeout.

10. **Window eligibility** — not every foreground HWND should be moved:
    fixed-size dialogs, tool windows, and the desktop/shell must be skipped;
    **UWP/Store apps** are hosted by `ApplicationFrameHost.exe` (the real frame
    is the host window, not the app's child).
    → Eligibility filter: require `WS_CAPTION`; treat `WS_THICKFRAME` absence as
    non-resizable (move-only, no resize); skip `WS_EX_TOOLWINDOW`; ignore the
    shell window (`GetShellWindow`) and cloaked windows
    (`DWMWA_CLOAKED`). For UWP, operate on the top-level frame HWND.

11. **Graceful shutdown** — a leaked low-level mouse hook and stuck global
    hotkeys persist past exit and degrade the whole OS.
    → On quit (tray "Exit", `WM_CLOSE`, `atexit`, and `SIGTERM`):
    `UnhookWindowsHookEx`, `UnregisterHotKey` for every id, release the
    single-instance mutex, and remove the tray icon. Wrap in try/finally so a
    crash still unwinds the hook.

---

## 6. Tech stack (all pip-installable on Windows)

- Python 3.11+
- **pywin32** — window + monitor + hotkey APIs
- **ctypes** (stdlib) — DPI awareness, DWM, low-level hooks
- **PySide6** — single GUI/event loop: tray (`QSystemTrayIcon`), preferences,
  shortcut recorder, snap overlay (replaces pystray/Pillow → fewer deps)
- **pytest** — tests (mock at ports; no real windows in CI)
- **PyInstaller** — single-file `.exe`
- (optional) **keyboard** lib as fallback hotkey backend

**CI:** GitHub Actions `windows-latest` runner — `core/` tests run anywhere;
adapter/integration tests require Windows (pywin32). Lint + type-check (ruff,
mypy) on `core`. **Single-instance guard:** named mutex (`CreateMutexW`) so a
second launch surfaces the existing tray icon and exits. **Distribution:**
unsigned exe triggers SmartScreen; v1 ships unsigned with a documented
"More info → Run anyway"; sign later with an EV/standard cert to clear it.

---

## 7. Delivery phases

- **P0 — Spike (~½ day):** prove move/resize of foreground window + one hotkey
  (`Ctrl+Alt+←` → left half) on real multi-monitor. De-risks DPI + border math.
- **P1 — Core engine (~2 days):** `core/` geometry + actions + tests. Halves,
  quarters, thirds, sixths, maximize, center, larger/smaller, gap.
- **P2 — Hotkeys + dispatch (~2 days):** full default shortcut map,
  repeat-cycling, undo.
- **P3 — Multi-monitor (~1 day):** move-to-display (preserve relative
  fraction), correct `rcWork` per monitor.
- **P4 — Tray + preferences (~2–3 days):** menu, JSON config, rebindable
  shortcuts, gap setting, launch-at-login.
- **P5 — Drag-to-edge snapping (~2–3 days):** mouse hook + footprint preview
  overlay.
- **P6 — Packaging (~1 day):** PyInstaller `.exe`, installer/Startup entry,
  icon, README.

Rough total: **~10–13 working days** for v1. Each phase: TDD on `core`, manual
verify on real windows for adapters.

---

## 8. Risks

| Risk | Mitigation |
|------|------------|
| DPI / invisible-border off-by-pixels | P0 spike validates before building wide |
| Low-level mouse hook flagged by AV | Sign the exe; document; hook is standard API |
| Admin-window limitation disappoints users | Document up front; optional elevated build |
| Reinventing Windows Snap/FancyZones | Lean on Rectangle's exact ergonomics as the draw |
| PySide6 packaging bloat in PyInstaller | Acceptable for v1; exclude unused Qt modules; consider `--onedir` |
| Win+arrow / OS-reserved hotkey clashes | Default map avoids Win+arrow; `RegisterHotKey` return checked; rebindable |

---

## 9. Definition of done (v1)

- All §2 actions work on Win 10 + Win 11, single and multi-monitor, mixed DPI.
- Shortcuts rebindable; config persists in `%APPDATA%`.
- Drag-to-edge snapping with preview + gap.
- Ships as one `.exe`, optional launch-at-login, tray menu with quit/prefs.
- `core` ≥90% unit-test coverage; adapters smoke-tested manually.

---

## Iteration log

- **v1** — Initial brief. Established non-literal-port approach, full
  macOS→Windows dependency mapping, hexagonal architecture, 7 hard problems
  with solutions, phased delivery.
- **v2** — Refinements: (a) MIT licensing note + attribution plan; (b) unified
  on a single PySide6 event loop — dropped pystray/Pillow, tray via
  `QSystemTrayIcon`; (c) added competing-event-loops + cycle/undo-identity as
  hard problems #8–#9; (d) overlay click-through/no-activate `WS_EX` flags;
  (e) move-to-display default changed off Win+arrow to avoid OS Snap clash;
  (f) added hotkey-clash risk row.
- **v3** — Added hard problem #10 window eligibility (UWP/ApplicationFrameHost,
  WS_CAPTION/WS_THICKFRAME/WS_EX_TOOLWINDOW filter, shell + cloaked windows);
  CI strategy (windows-latest, core portable / adapters need Windows);
  single-instance mutex; unsigned-exe / SmartScreen distribution note.
  Brief now covers reality, parity, full dependency mapping, architecture,
  10 hard problems, stack, CI, phases, risks, DoD — **assessed converged.**
- **v4** — Final correctness/planning items: hard problem #11 graceful
  shutdown (unhook/unregister/release mutex/remove tray on exit + crash unwind);
  per-phase effort estimates (~10–13 days total); move-to-display preserves
  relative fraction. Remaining candidate edits are padding, not improvement —
  **brief is converged; loop stopped.**
- **v5** — Post-converge user-experience pass (brief is a spec; the app
  still needed packaging + onboarding):
  (a) `README.md` separates user docs from this technical brief;
  (b) `Build-Exe.ps1`/`.bat` produce `dist\WindowsRectangle.exe` in one
  shot — auto-installs PyInstaller / PySide6 / pywin32 if missing; the
  PS variant supports `-InstallStartMenuShortcut` for per-user Start
  Menu entry;
  (c) `Run-Dev.ps1`/`.bat` are the from-source fast path for
  contributors;
  (d) tray gains Cheat sheet…, About…, **Reload config from disk**,
  **Open config folder…** entries; programmatic 4-pane blue icon
  replaces the white-square placeholder; first-run welcome balloon
  fires when `bind_win32` detects no existing config file;
  (e) `AppContext` exposes `first_run`, `reload_config()`, and
  `config_folder()` so tray + tests share a single source of truth.
</content>
</invoke>
