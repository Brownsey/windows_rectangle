# Contributing

Thanks for considering a contribution. The fast path:

```powershell
# 1. Clone + set up
git clone https://github.com/Brownsey/windows_rectangle.git
cd windows_rectangle
python -m pip install -e ".[dev,win]"

# 2. Run the tests
python -m pytest

# 3. Run from source (tray UI)
python -m windows_rectangle
# or:
.\Run-Dev.ps1
```

Everything in `core/` + `ports/` is pure Python and tests on any
platform. The Win32 adapters require Windows but are mocked at the port
boundary in tests — most contributions don't need a real Windows host
to validate.

## Project layout

See `BRIEF.md` §4 for the hexagonal/ports-and-adapters layout. The
short version:

```
windows_rectangle/
├── core/        # pure logic — Rect math, action transforms, dispatcher
├── ports/       # Protocols / ABCs — window manager, hotkeys, config
├── adapters/    # Windows-specific implementations
├── ui/          # PySide6 tray, prefs dialog, overlays, formatters
├── app.py       # composition root — wires ports↔adapters into AppContext
└── __main__.py  # CLI entry point (`python -m windows_rectangle`)
```

`core/` imports nothing OS-specific; `adapters/` is where pywin32 +
ctypes live; `ui/` lazy-imports PySide6.

## Conventions

- **Lazy Qt imports.** Anything under `ui/` must be importable without
  PySide6 installed. Push `from PySide6 import …` inside the function
  that builds the widget.
- **Pure formatters live next to lazy Qt widgets.** `ui/cheat_sheet.py`
  and `ui/binding_status_view.py` are pure; `ui/tray.py` consumes them.
  This keeps wording + escaping unit-tested without a QApplication.
- **Adapter side-effects gated behind a `best_available()` factory.**
  See `adapters/winreg_autostart.py` for the pattern — non-Windows
  hosts return a memory-backed fake.
- **No `# type: ignore` without a comment.** mypy strict mode is the
  baseline for `core/`; widening lives in `pyproject.toml`.

## Running the tests

```powershell
python -m pytest                          # 460+ tests, ~5s
python -m pytest tests/test_diagnostics.py  # one module
python -m pytest -k "binding"             # by name
python -m pytest --co -q                  # list test ids
```

If you only touch `core/`, you can skip `[win]` extras entirely — the
adapter tests fake the Windows side.

## Checking your install

Before opening an issue about a runtime problem, confirm your
environment with the self-diagnostic:

```powershell
python -m windows_rectangle --check-install
```

It prints version, dep importability, config path, and exits 0/1 so
you can pipe it into CI.

## What changes need a brief update?

`BRIEF.md` is the architectural spec — bump the iteration log when you
change something the brief describes (a new "hard problem", a different
boundary, a new port). Day-to-day feature changes go to `CHANGELOG.md`.

## CI

The GitHub Actions workflow at `.github/workflows/ci.yml` runs pytest
on the `windows-latest` runner. Adapter tests need Windows; `core/` and
`ports/` tests would pass anywhere.

## Pull-request checklist

- [ ] Tests added / updated for the new behaviour.
- [ ] `python -m pytest` passes locally.
- [ ] `python -m windows_rectangle --check-install` reports OK on your dev box.
- [ ] `CHANGELOG.md` (Unreleased) updated if the change is user-visible.
- [ ] `BRIEF.md` iteration log bumped if the architectural surface changed.
