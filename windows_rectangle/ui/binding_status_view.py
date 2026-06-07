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
    """
    if report is None or report.total == 0:
        return "No hotkey binding has run yet."
    lines = [
        f"{report.bound_count} of {report.total} shortcuts bound.",
        "",
    ]
    if report.bound:
        lines.append("Bound:")
        lines.extend(f"  {action.value:<28} {combo}" for action, combo in report.bound)
        lines.append("")
    if report.failed:
        lines.append("Failed:")
        for action, combo, err in report.failed:
            err_brief = err.strip().splitlines()[0] if err else ""
            lines.append(f"  {action.value:<28} {combo}   ← {err_brief}")
    return "\n".join(lines).rstrip()


def binding_status_html(report: "BindingReport | None") -> str:
    """HTML rendering for QMessageBox.setText.

    All combo/error strings are HTML-escaped. The bound and failed
    sections render as separate small tables for readability.
    """
    if report is None or report.total == 0:
        return "<p>No hotkey binding has run yet.</p>"

    parts: list[str] = []
    summary = (
        f"<p><b>{report.bound_count}</b> of <b>{report.total}</b> "
        "shortcuts bound."
    )
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
        parts.append(
            f"<h4 style='{_HEADER_STYLE}'>Bound</h4>"
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
