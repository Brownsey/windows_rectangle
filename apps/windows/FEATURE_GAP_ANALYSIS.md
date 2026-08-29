# Feature Gap Analysis

This review compares the Windows app against Windows 11 Snap Layouts,
Microsoft PowerToys FancyZones, and AquaSnap.

Sources reviewed:

- Windows Snap: https://support.microsoft.com/en-us/windows/experience/snap-your-windows
- PowerToys FancyZones: https://learn.microsoft.com/en-us/windows/powertoys/fancyzones
- AquaSnap: https://www.nurgo-software.com/products/aquasnap

## Already Covered

| Capability | Status |
| --- | --- |
| Halves, quarters, thirds, two-thirds, sixths | Implemented |
| Keyboard-driven window placement | Implemented |
| Editable shortcut UI with recording | Implemented |
| Drag-to-edge snapping preview | Implemented |
| Multi-monitor next/previous display movement | Implemented |
| Gaps between windows | Implemented |
| Restore last window position | Implemented |
| Larger/smaller resizing | Implemented |
| Maximize height | Implemented |

## Added From This Review

| Capability | Why |
| --- | --- |
| Maximize width | Matches the directional stretching class of behavior in AquaSnap. |
| Always on top | AquaSnap exposes utility window-management behavior beyond tiling. |
| Safer shortcut profile | Avoids Windows-owned `Ctrl+Win` combinations during repeated input. |
| Hotkey storm throttling | Prevents rapid shortcut input from monopolizing the UI thread. |

## Still Missing

| Capability | Comparable product | Implementation shape |
| --- | --- | --- |
| Custom zone layouts | FancyZones | Add a `zones` domain model, persisted layout definitions, a layout editor tab, and actions for applying a window to selected zones. |
| Snap to multiple zones | FancyZones | Represent target as a union of adjacent zones and add keyboard/mouse selection state. |
| Quick layout switching | FancyZones | Add numbered layout profiles and bindable layout-switch actions. |
| Snap Assist / fill remaining windows | Windows Snap | Requires enumerating visible windows, ranking candidates, and a chooser UI. |
| Snap groups | Windows Snap | Requires tracking window sets and restoring multiple windows together. |
| Adjacent-window resizing | Windows Snap, AquaSnap | Requires detecting neighboring windows and resizing both sides of a shared edge. |
| Magnetic alignment to other windows | AquaSnap | Requires live window enumeration while dragging and edge-proximity snapping. |
| Move adjacent window group together | AquaSnap | Requires grouping adjacent windows and applying deltas to all group members. |
| Mouse titlebar shortcuts | AquaSnap | Requires titlebar hit testing or low-level mouse handling over non-client areas. |

The next large feature should be custom zones. It would subsume much of the
FancyZones gap and gives a clear path to multi-zone snapping, quick layout
switching, and layout import/export.
