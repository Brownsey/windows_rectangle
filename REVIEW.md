# Windows code review and performance analysis

## Runtime and experience iteration — 1 October 2026

The follow-up starts from `2fbbcf4` and targets measured tray-runtime work and
observed interaction failures. It retains the existing Qt design and adds no
dependencies. The measurements below describe local source runs; they do not
replace the earlier executable's separately identified release evidence.

### Runtime measurements

The normal tray runtime was measured with the native mouse hook installed and
default shortcuts requested. Both runs bound 23 shortcuts; five were rejected
because other applications already held them. Each process used isolated
configuration, disabled registry synchronization and left the user's Run entry
unchanged. After two seconds of settling, the probe sampled process CPU time,
`QueryProcessCycleTime`, memory and actual Qt drain/paint events for 20 seconds.

| Metric | Continuous polling | Queued wakeups |
| --- | ---: | ---: |
| Action/drag drain calls | 1,248 | 0 |
| Process cycles | 1,701,204,878 | 3,131,816 |
| Process CPU time | 0.0938 s | Below the observed 15.625 ms accounting resolution |
| Working set at end | 52.72 MiB | 53.06 MiB |
| Qt paint events | 0 | 0 |

The paired sample recorded approximately 99.8% fewer process cycles while idle.
This is a local idle result, not a whole-application speedup or a claim of zero
CPU usage. The stronger structural evidence is that no periodic action/drag
drain runs while idle. Queued notifications wake the UI for work; the 16 ms
timer remains active during dragging and queued batches. Maintenance has its
own minute-scale timer. Mouse motion does not flood Qt with queued signals.
Maintenance restarts its single-shot timer after cleanup so late timer delivery
cannot cause the next cleanup to be skipped by the internal rate limit.
The implementation follows Qt's
[queued receiver-thread delivery and timer ownership rules](https://doc.qt.io/qt-6/threads-qobject.html).

A further native-adapter run delivered a synthetic completed-click callback
before sampling. It recorded zero subsequent drain/paint calls over 20 seconds,
1.43 million process cycles and a stable 53.39 MiB working set. This confirms
return to idle after the completed-click state; it is not a physical mouse-input
test. The hook remained installed, and the user's registry setting was unchanged.

A second probe compared the committed polling entry point with the new entry
point using the same core and fake window manager. A worker submitted 100
actions at varying phases, and the actual Qt loop dispatched them. Submission
to window-manager invocation fell from **7.935 ms median / 15.185 ms p95** to
**0.318 ms median / 0.700 ms p95**. This isolates scheduling latency; it excludes
physical keyboard input, native window movement and compositor presentation.

The optional headless runtime also wakes on queued input. In paired native-input
idle samples of approximately 20 seconds, drain calls fell from 464 to 76 and
process cycles from 97,773,042 to 29,844,428 (about 69.5% fewer). Working set stayed
near 22 MiB. Its idle wait is capped at 250 ms to keep Ctrl+C responsive on the
supported Windows/Python 3.13 runtime; active work retains 30 Hz polling. The
signal handler only sets a flag. Controlled-clock tests verify scheduling and
actual maintenance, and a bounded subprocess test exercises SIGINT cleanup.

The native overlay was also measured with synthetic snap coordinates. Over a
six-second stationary preview, 376 input ticks caused **zero repeated show,
hide or paint calls**. Twelve size-changing zone transitions caused twelve
paints, taking 0.140625 seconds of process CPU time over six seconds (2.344% of
one core). Same-size position changes reused the painted surface. No rendering
rewrite was justified by these results.

GPU Engine counters returned 861 valid engine samples but no instance for the
overlay process; the normal tray probes likewise exposed no process instance.
**GPU utilization is unmeasured**, not zero. Desktop compositor work can belong
to another process. These observations establish paint suppression, not an
end-to-end GPU utilization percentage.

Local evidence and runnable probes are retained under ignored `build/review`:
`profile_source_runtime.py`, `source-runtime-before-scheduler.json`,
`source-runtime-baseline.json`, `dispatch_latency_probe.py` and
`overlay_runtime_probe.py`, with their JSON outputs. The completed-click run is
`profile_source_runtime_after_click.py` and `source-runtime-after-click.json`.

### Native UI audit

The audit exercised the actual Qt widgets against an isolated JSON store and
controlled window/hotkey adapters. Native Windows captures contained readable
fonts; earlier offscreen captures with missing glyphs were excluded from visual
conclusions. Keyboard traversal, shortcut duplicates, failed saves, persistence
after reopening, workspace creation, matching and restore were exercised.

This iteration fixes the observed issues:

- Preferences must show saved shortcuts that Windows could not register and
  offer retry without changing or writing settings. Retry must preserve dirty
  edits, use current saved settings and respect pause. External text must remain
  literal text rather than Qt markup.
- Editing a workspace rule must invalidate its previous match result.
- Restore feedback must distinguish full success, partial restoration and no
  windows moved, including blocked moves.
- A successful save after failure must update the visible workspace name.
- Workspace controls must remain reachable on a 960×520 logical desktop.

The complete source gate passed on Windows/Python 3.13.13: **809 tests**, Ruff
lint and formatting (112 files), and strict mypy checks (21 core source files).
Native Qt integration, isolated JSON persistence and 200% scale layout checks
cover the changed interactions. Source performance measurements do not verify
a newly packaged executable. The release hashes and executable measurements in
the historical review below apply only to that earlier snapshot.

Review date: 30 September 2026. Baseline: `cfbd77d`. Scope: the complete
repository, with implementation and validation concentrated on the Windows
runtime, persistence, native boundaries, UI, launchers and packaging.

The repository now has one Windows implementation and one test tree. The
vendored upstream application, obsolete build workflow, duplicate Python source
and tests, tracked coverage data and local assistant configuration were removed.
Upstream attribution remains in `THIRD_PARTY_NOTICES.md`.

## Acceptance criteria

1. Only the Windows application is built and documented; canonical source and
   tests live under `apps/windows`.
2. Native input callbacks remain bounded and perform no window manipulation.
   A snap targets the window actually dragged and the rectangle previewed;
   content selection, resizing and cancelled drags do not snap another window.
3. Invalid settings cannot replace a valid configuration. Failed window moves
   retain undo history. Workspace edits preserve unrelated concurrent settings.
4. Closing Preferences leaves the tray application running. Documented launch
   modes, shortcut editing and persistence work through the actual Qt widgets.
5. Native handles, hooks and registration threads have truthful failure results
   and deterministic cleanup. A second instance does not start native workers.
6. Repository checks run with Qt installed, and packaging uses the checked-in
   spec and exercises the actual executable. Performance claims have a runnable
   benchmark or a clearly identified structural basis.

### Follow-up iteration criteria

- P1: Preserve deterministic maximum-cardinality workspace assignment, Unicode
  and regex matching, enumeration order and duplicate-handle protection.
- P2: Reduce measured matching CPU cost against the corrected algorithm on
  small, large, overlapping and missing-window workloads without dependencies.
- U1: Reverting a Preferences edit restores the saved state and disables save
  actions, while concurrent changes remain preserved.
- U2: Search has an explicit empty state and usable keyboard/accessibility
  behavior within the existing visual design.
- U3: General-only saves avoid unnecessary native shortcut registration without
  breaking shortcut changes, recording, pause or failed-registration recovery.
- U4: Preferences fits the available desktop at 200% scaling on a 1920×1080
  display, with save actions reachable and the shortcut list scrollable.

These changes retain the high-risk validation gate because the wider review
touches native integrations and settings persistence: affected checks followed
by a distinct read-only final review. Timing uses frozen baselines; packaged
startup and idle measurements use isolated configuration and disposable app
processes, preserving the existing login registry setting.

## Findings and changes

| Area | Finding | Correction and proof |
| --- | --- | --- |
| Dragging | A left-button content drag could trigger snapping; the final action could select a different foreground window or cycle to another size. | Observe the native move/size loop, capture its HWND, distinguish translation from resizing, and dispatch the exact preview target. Regression coverage in `test_drag_pipeline.py`. |
| Drag release | Throttling could omit final cursor coordinates; the OS move loop could overwrite a snap applied too early. | Consume release coordinates regardless of throttle and wait for the native loop to end before applying the target. |
| Input latency | Hook callbacks performed work that belongs on the UI thread; continuously replenished queues could monopolize a timer tick. | Hook writes one immutable latest-state snapshot. The main thread polls it; action drains are bounded to 16 and workspace drains to one per tick. |
| Latest-value handoff | A producer could publish between a consumer's read and clear, losing the newer value. | Replace the split operation with a bounded deque and exercise a forced producer/consumer interleaving. |
| Native ABI | Several ctypes calls used implicit pointer-sized argument or return conventions. | Declare Win32 signatures, including hook LRESULT and handle cleanup. Adapter tests and disposable native-window probes cover these boundaries. |
| DPI awareness | A negative DPI context was passed as a 32-bit integer on x64, silently falling back from Per-Monitor V2. | Declare its pointer-sized argument; a fresh-process Windows test now observes Per-Monitor V2. |
| Native lifecycle | Hook installation or message-pump failure could be reported as success; dead workers could cause repeated request timeouts. | Startup errors propagate, liveness and wake results are checked, timed-out queued requests are cancelled, and thread exits release native registrations. |
| Window geometry | Visible-bound reads did unnecessary fallback work; monitor transfer could fail for an offscreen window. | Query DWM bounds first and fall back only when needed; preserve dimensions and fit offscreen transfers into the destination work area. |
| Always on top | The topmost toggle still used synchronous positioning, unlike window movement. | Include `SWP_ASYNCWINDOWPOS` while retaining size, position and activation. Four regression cases verify enabled/disabled and accepted/rejected requests. |
| Undo | Failed moves could consume or corrupt history. | Record successful forward moves only; peek before undo and remove the entry only after an accepted move. |
| Configuration | Syntactically valid JSON with invalid shapes or values could crash startup or replace valid settings during import. | Validate containers, scalars, booleans, ranges and finite numbers. Startup falls back without rewriting the bad file; explicit import rejects it. |
| Workspaces | Broad rules could consume a window needed by a narrower rule; a specificity heuristic still missed feasible assignments. | Cache candidate matches and use deterministic augmenting reassignment, with the fewest-candidate rules first. Preserve placement output order and assign each HWND only once. |
| Workspace editing | An unchanged rename could raise KeyError; a stale editor snapshot could overwrite newer general preferences. | Treat no-op changes safely and merge workspace-owned fields into current settings, checking concurrent workspace changes. |
| Concurrent preferences | Applying a gap edit could undo a newer tray login setting or unrelated shortcut change. | Merge only controls and shortcut actions edited against the last loaded baseline, then reload the applied state. |
| Preferences feedback | Reverting an edit left Save/Apply enabled; an unmatched search looked blank. | Derive dirty state from baseline differences, show an explicit empty state, focus search with Ctrl+F from either tab and clear it with Escape while focused. |
| Preferences save cost | A general-only save unnecessarily re-registered every shortcut. | Skip the extra native rebind when healthy; retain retry for prior failures and the normal rebind path for changed shortcuts. |
| Imported preference values | Widget rounding and shortcut capitalization could falsely mark untouched values as edits. Some mixed-case Windows/Page Up bindings appeared blank. | Compare against the actual loaded widget representation, preserve untouched stored values, and normalize shortcuts before Qt conversion. |
| Merged validation | The legacy controller returned validation for its staged snapshot rather than the final merged settings. | Validate the merged candidate before callbacks, retaining the existing warning-only duplicate policy. |
| Enlarged display scaling | A fixed 820×620 minimum exceeded the usable desktop at 200% scaling. | Use a smaller minimum and cap initial dimensions to available screen space. A fresh Windows Qt process verifies the frame and Apply button fit. |
| Window disappearance | A window closing during capture could abort the operation. | Skip failed individual captures while retaining valid entries. |
| Pausing | Editing bindings while shortcuts were paused could register them again. | Keep native bindings empty until explicit resume, with an accurate paused status report. |
| UI lifecycle | Closing the last Qt window could quit the tray utility. | Disable quit-on-last-window-close and retain explicit Quit cleanup. |
| Overlay | Physical Win32 target coordinates were passed through Qt logical-coordinate placement. | Place the native overlay HWND in physical pixels. Verify actual HWND bounds. |
| Preferences and CLI | Previously skipped Qt tests exposed missing documented search/shortcut-recording UI and launch switches. | Exercise the actual modeless preferences window and route startup/tray entry points through it. |
| Startup | Autostart lacked a dependable executable/module command; a second instance could initialize workers before checking the mutex. | Quote the source/frozen command with explicit tray mode, and acquire the instance guard before config changes or thread creation. |
| Scripts | The stop script could kill other Python work merely because its command line contained the repository path. | Require the application module/entry point or executable. A subprocess regression includes unrelated test and build processes. |
| Packaging | The release path bypassed the maintained spec, and a GUI import failure could pass a packaged diagnostic. | Use one onedir spec, bundle notices/logos, honor exclusions, and require actual Qt GUI imports in frozen diagnostics. |
| Build failure propagation | PowerShell could report success before a GUI-subsystem executable's failed smoke test completed. | Wait for the actual process and inspect its exit code. A real `pythonw.exe` failure regression verifies rejection. |
| DLL collection | An unrelated tool's `icuuc.dll` on PATH shadowed the Windows ICU API and broke frozen Qt imports. | Prefer System32 during PyInstaller analysis, then restore PATH. The regression checks search order; the real executable is the decisive smoke test. |
| Dependencies | The runtime requested all PySide6 modules and an unused pywin32 package. | Request only `PySide6-Essentials`; Win32 calls use stdlib ctypes. QtTest remains available for tests. |

The ICU failure was reproduced in the executable and narrowed with PE
import/export inspection: the unrelated DLL lacked 20 imports requested by
QtCore. The application uses [Windows' ICU API](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-).
The correction changes build-time search order; it does not alter system DLLs.

## Performance evidence

Run the matching comparison with:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark-windows.py
```

It freezes the corrected maximum-cardinality algorithm as the timing baseline,
verifies equivalent results, and tests unique, overlapping and missing-window
workloads. The original greedy matcher remains only as an additional unique-case
equivalence check. Five batches use enough iterations to reduce Windows process
CPU accounting quantization; the median is reported per workspace. It measures
matching CPU time, not native movement or end-to-end UI latency.

The earlier corrected matcher was slower than the original greedy algorithm
on unique matches. Profiling traced the cost to repeated normalization of each
rule/window pair and sorting equal scores. Normalizing each window and rule
once, then collecting candidates in enumeration order, retains the assignment
algorithm while removing that work.

| Workload | Corrected baseline | Optimized | CPU reduction |
| --- | ---: | ---: | ---: |
| 10 unique windows | 0.227 ms | 0.086 ms | 62% |
| 100 unique windows | 14.688 ms | 3.438 ms | 77% |
| Overlapping regex rules | 0.062 ms | 0.044 ms | 29% |
| Missing windows | 0.188 ms | 0.078 ms | 59% |

These are local synthetic measurements, not universal application speedups or
service-level guarantees. Tests also check Unicode casefolding, regex behavior,
stable ordering and exhaustive small overlap cases against a maximum-matching
oracle.

The input path now has constant retained state rather than a growing stream of
mouse-move events. No monitor enumeration, DWM lookup or Qt mutation occurs in
the hook callback. Polling still uses the existing approximately 60 Hz timer;
idle polling and OS scheduling remain costs. Limiting queued work improves
fairness, but does not put a hard time limit on an individual native operation.

DWM visible-bounds reads now avoid a redundant `GetWindowRect` call when DWM
succeeds. These are structural reductions backed by behavior tests; no
unsupported whole-application CPU or memory percentage is claimed.

Correct workspace assignment takes priority over a greedy scan. The final
matcher evaluates each rule/window pair once and can reassign overlapping
candidates to avoid false misses. Matching remains synchronous, so large rule
sets and costly user regexes should be profiled with real workloads.

The portable folder avoids one-file extraction on every launch. Essentials
reduces dependency installation scope; release size and startup latency must be
measured separately from download size.

The final executable reached its own visible Preferences window in **2.266,
3.104 and 4.193 seconds** (median **3.104 s**). After a one-second settling
period, each five-second idle sample reported zero CPU-time delta at the
observed Windows accounting resolution; this means below that resolution,
not literally no work. Working sets remained stable at **128.27–130.99 MiB**.
These isolated runs disabled shortcut bindings and dragging, so they do not
establish default-hook idle cost or active snapping latency. Startup varies
with host load and file caching; no startup speedup is claimed from these
three samples. The reproducible local probe and raw results are retained in
`build/review/measure_frozen_gui.py` and `frozen-gui-performance.json`.

## Validation record

Local environment: Windows 10 build 19045, x64, Python 3.13.13, Qt 6.11.2,
pytest 9.1.1, Ruff 0.16.9, mypy 2.3.1 and PyInstaller 6.22.3.

The canonical `scripts/check.ps1` completed with Ruff lint and formatting clean,
strict mypy clean across the 21 core files, and **755 tests passing without
skips**. Type checking currently covers the pure core, not the dynamic Qt or
ctypes adapters; those boundaries rely on tests and independent review.

The final dependency environment contains Essentials and shiboken, with neither
the full PySide6/Addons packages nor pywin32 installed. `pip check` is clean.
`pywin32-ctypes` remains a separate build dependency of PyInstaller, not an
application runtime requirement.

The reviewed source/test/build snapshot covers 121 files, recorded locally in
`build/review/snapshot.json`: SHA-256
`7f1bdd5f316426d26ff01cd9ca901e1193dc3799afa6ec4db3d53cba07ea8ce7`.
The implementation snapshot is compared against the baseline listed above.

The canonical build completed successfully after the full gate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-windows.ps1 -NoInstall
```

The final executable's `--check-install-json` returned exit 0 and all eight
required imports passed. ZIP integrity and both generated SHA-256 checksums
were independently checked. The archive contains the Windows Qt platform plugin.
The portable runtime is 96,615,973 bytes (about 92.1 MiB); its ZIP is
40,275,143 bytes (about 38.4 MiB). Distribute the ZIP or the entire folder,
not the executable by itself.

- Executable SHA-256: `9e2fd19363c43fa2d398c53ca800aeecd39ffe847cb84666589adcfe2cca841f`
- ZIP SHA-256: `ad9f6d444c5afd2527590590598b43c87888c28d2754d4ad3bfdef1e6085298c`

An independent validator then launched the actual frozen executable with
isolated temporary configuration and no active shortcuts or drag hook. Its
Preferences HWND became visible and exited with code 0 after a graceful quit
message in all three final-build runs. Earlier native and frozen checks
confirmed Per-Monitor V2 through the window-context API; that DPI code is
unchanged, and its source regression passes in the final full gate.
The existing login registry state was read before startup, matched in the
temporary settings and verified unchanged afterward. The temporary config was
removed. Package diagnostics and native integration tests also pass with
pywin32 uninstalled. All 202 files in the archive were checked byte-for-byte
against the release folder, in addition to ZIP integrity and checksum checks.

A distinct final read-only reviewer reproduced and rechecked the concurrent
Preferences, numeric-overflow, overlapping-rule and x64 DPI defects. Those
findings and the unused dependency finding are resolved. The follow-up review
also caught imported-value precision, shortcut representation and scaled layout
defects; fixes passed the fresh 755-test gate and independent affected checks.
No confirmed Critical or Important source finding remains in the final reviewed
snapshot.

Independent validation exercised a disposable real HWND, visible rectangle
placement, uniquely named mutex acquisition/release, hotkey registration and
release, and actual mouse-hook install/shutdown. It also exercised modeless
Preferences search, shortcut editing, Save, JSON reload, close and reopen using
isolated temporary configuration. No user windows were moved and no login
registry setting was changed.

The native Qt visual check inspected a 920×700 window and corrected an initially
low-contrast logo. The final [Preferences screenshot](research/windows-preferences.png)
and [empty-search screenshot](research/windows-preferences-empty-search.png)
are retained as review evidence. A separate process at `QT_SCALE_FACTOR=2`
reported a 960×520 logical work area and a fitting 920×488 window frame;
the [200% screenshot](research/windows-preferences-scaled.png) shows reachable
bottom actions. This changes only that process's scale, not Windows settings.
Follow-up independent validation passed **212
affected tests**, including real JSON persistence, keyboard behavior and native
topmost toggling on a disposable HWND. After the final precision, imported-key
and scaling corrections, an additional **153 affected tests** passed. The
independent [scaled General view](research/windows-preferences-general-scaled.png)
also confirms that all controls and bottom actions remain visible. The Qt tests ran with the GUI dependency
installed; the initial baseline had skipped all 16 Preferences widget tests.

GitHub Actions now targets Windows with Python 3.11 and 3.13. The remote matrix
has not been run in this session. Native integration tests require a usable
Windows desktop; no CI-specific skips were added.

## Boundaries and further measurement

The local host has one 1920×1080 display. Automated geometry tests cover negative
coordinates and multiple monitor layouts, but they do not replace physical
mixed-DPI, display-hotplug, portrait and multi-monitor drag trials. The drag
guard deliberately rejects observed size changes while the button is held;
cross-DPI size transitions need that hardware trial.

Elevated target applications, unresponsive third-party GUI threads, remote
desktop sessions and a clean Windows installation need a release smoke matrix.
An accepted native positioning request does not prove every target application
will retain that size: applications may enforce their own minimum dimensions or
subsequently move themselves. `ShowWindowAsync` prevents a restore request from
waiting on another GUI thread, but subsequent native operations are not all
asynchronous. See [Microsoft's API contract](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindowasync).

Workspace capture still queries monitor identity per window. A snapshot-based
adapter could reduce enumeration if profiling large captures shows meaningful
cost, with explicit handling of topology changes. User-supplied regular
expressions also have input-dependent matching cost. Neither speculative
caching nor a new matching dependency was introduced without measured need.

A read-only local measurement of `list_monitors()` on this one-display host
used five batches of 100 calls: the median was **0.088 ms per enumeration**.
This does not justify adding topology cache invalidation to the current app.
The topmost toggle now uses the asynchronous positioning flag documented by
[Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos)
to avoid waiting for a target thread on a different input queue; it does not
guarantee completion by an unresponsive target application.

General-only Preferences saves now skip shortcut registration when existing
bindings are healthy. Previously failed registrations still retry; changed
shortcuts continue through the application's normal apply path. Reverted edits
disable save actions, and search now explains empty results and supports
keyboard focus and clearing.

This review establishes an evidence-backed improvement over the recorded
baseline. It cannot prove that no future correctness or performance improvement
is possible.
