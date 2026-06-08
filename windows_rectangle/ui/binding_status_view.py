"""Binding-status renderer — turn a `BindingReport` into HTML/plain text.

Pure formatter — Qt is not imported. The tray (`ui/tray.py`) lazy-imports
this when the user clicks "Binding status…" and pipes the result into a
QMessageBox.

Keeping the formatter separate from the Qt wiring means we can lock in
the wording (and HTML escaping) via tests without spinning up a
QApplication.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import BindingReport


_HEADER_STYLE = "margin: 6px 0 4px 0;"


def binding_status_text(report: "BindingReport | None") -> str:
    """Plain-text rendering — useful for logs and tests.

    None / empty report renders the same way ("no binding has run yet"),
    so the function is total over the possible inputs.

    When `report.paused` is True the section labelled "Bound" instead
    renders as "Would re-register on resume" since the entries are not
    currently live.
    """
    if report is None or report.total == 0:
        if report is not None and report.paused:
            return "Hotkeys are paused — no combos are currently registered."
        return "No hotkey binding has run yet."
    paused = report.paused
    summary = (
        f"{report.bound_count} of {report.total} shortcuts bound"
        + (" (paused)." if paused else ".")
    )
    lines = [summary, ""]
    if report.bound:
        lines.append(
            "Would re-register on resume:" if paused else "Bound:"
        )
        lines.extend(f"  {action.value:<28} {combo}" for action, combo in report.bound)
        lines.append("")
    if report.failed:
        lines.append("Failed:")
        for action, combo, err in report.failed:
            err_brief = err.strip().splitlines()[0] if err else ""
            lines.append(f"  {action.value:<28} {combo}   <- {err_brief}")
    return "\n".join(lines).rstrip()


def binding_status_html(report: "BindingReport | None") -> str:
    """HTML rendering for QMessageBox.setText.

    All combo/error strings are HTML-escaped. The bound and failed
    sections render as separate small tables for readability.
    """
    if report is None or report.total == 0:
        if report is not None and report.paused:
            return "<p>Hotkeys are <b>paused</b> &mdash; no combos are currently registered.</p>"
        return "<p>No hotkey binding has run yet.</p>"

    paused = report.paused
    parts: list[str] = []
    summary = (
        f"<p><b>{report.bound_count}</b> of <b>{report.total}</b> "
        "shortcuts bound"
    )
    if paused:
        summary += " <span style='color:#a60;'>(paused)</span>"
    summary += "."
    if report.failed:
        summary += f" <span style='color:#b22;'>{report.failed_count} failed.</span>"
    summary += "</p>"
    parts.append(summary)

    if report.bound:
        rows = "".join(
            f"<tr><td>{html.escape(a.value)}</td>"
            f"<td><kbd>{html.escape(c)}</kbd></td></tr>"
            for a, c in report.bound
        )
        header_label = "Would re-register on resume" if paused else "Bound"
        header_colour = "color:#888;" if paused else ""
        parts.append(
            f"<h4 style='{_HEADER_STYLE}{header_colour}'>{header_label}</h4>"
            "<table cellspacing='4' cellpadding='2'>"
            f"<tbody>{rows}</tbody></table>"
        )

    if report.failed:
        rows = "".join(
            f"<tr><td>{html.escape(a.value)}</td>"
            f"<td><kbd>{html.escape(c)}</kbd></td>"
            f"<td style='color:#b22;'>{html.escape(e.splitlines()[0] if e else '')}</td>"
            "</tr>"
            for a, c, e in report.failed
        )
        parts.append(
            f"<h4 style='{_HEADER_STYLE}; color:#b22;'>Failed</h4>"
            "<table cellspacing='4' cellpadding='2'>"
            f"<tbody>{rows}</tbody></table>"
        )

    return "".join(parts)
