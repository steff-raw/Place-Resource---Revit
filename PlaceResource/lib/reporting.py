# -*- coding: utf-8 -*-
"""pyRevit output reports. Printing never changes the model."""


def print_plan(plan, definition):
    """Print the pre-commit summary for one source view."""
    collection = plan["collection"]
    lines = [
        "# Legend preview",
        "",
        "Definition: **{0}**".format(definition["display_name"]),
        "Mode: {0}".format(plan["mode"]),
        "Visible instances: {0}".format(collection.instance_count),
        "Unique types: {0}".format(collection.unique_type_count),
        "Existing legend: {0}".format(plan["existing_name"] or "None"),
        "Views collected: {0}".format(", ".join(collection.view_info.get("source_views") or []) or "Active view"),
        "",
        "## Types",
    ]
    _print_md("\n".join(lines))
    rows = []
    for record in collection.types:
        rows.append([
            record.display.get("Type Mark") or "",
            record.type_name,
            record.family_name,
            str(len(record.instance_ids)),
            record.display.get("Fire Rating") or "",
            record.display.get("Width") or "",
        ])
    _print_table(rows, ["Type Mark", "Type Name", "Family", "Instances", "Fire Rating", "Width"])
    if plan["to_add"]:
        _print_md("\n## New rows\n")
        for record in plan["to_add"]:
            _print_md("- {0}".format(record.type_name))
    if plan["to_remove"]:
        _print_md("\n## No longer visible\n")
        for type_id in plan["to_remove"]:
            _print_md("- type id {0}".format(type_id))
    _print_messages("Excluded", _excluded_lines(collection))
    _print_messages("Warnings", collection.warnings)
    _print_messages("Notices", collection.notices[:8])
    block = plan["estimate"]["block"]
    _print_md(
        "\nRough size: {0:.0f} x {1:.0f} mm. Final spacing is set once the legend is "
        "made.".format(block["width"] * 304.8, block["height"] * 304.8)
    )


def print_report(report):
    """Print the result of one create or update."""
    _print_md("\n".join([
        "# Legend {0}".format(report.get("status")),
        "",
        "- View: {0}".format(_link(report.get("source_view_id"), report.get("source_view_name"))),
        "- Legend: {0}".format(_link(report.get("legend_view_id"), report.get("legend_view_name"))),
        "- Legend type: {0}".format(report.get("definition_name")),
        "- Elements found: {0}".format(report.get("instance_count")),
        "- Types found: {0}".format(report.get("unique_type_count")),
        "- Rows added: {0}".format(len(report.get("added") or [])),
        "- Rows updated: {0}".format(len(report.get("updated") or [])),
        "- Rows removed: {0}".format(len(report.get("removed") or [])),
        "- Rows lined up: {0}".format(report.get("realigned")),
        "- Revit: {0}".format(report.get("host")),
        "- Tool version: {0}".format(report.get("version")),
    ]))
    _print_messages("Added", report.get("added") or [])
    _print_messages("Updated", report.get("updated") or [])
    _print_messages("Removed", report.get("removed") or [])
    _print_messages("Warnings", report.get("warnings") or [])
    _print_messages("Errors", report.get("errors") or [])
    _print_messages("Notices", (report.get("notices") or [])[:12])


def print_batch(summary):
    """Print the project-wide update summary."""
    _print_md("\n".join([
        "# Update all legends",
        "",
        "- Status: {0}".format(summary.get("status")),
        "- Updated: {0}".format(len(summary.get("updated") or [])),
        "- Unchanged: {0}".format(len(summary.get("unchanged") or [])),
        "- Skipped: {0}".format(len(summary.get("skipped") or [])),
        "- Failed: {0}".format(len(summary.get("failed") or [])),
    ]))
    for bucket, title in (("updated", "Updated"), ("unchanged", "Unchanged"),
                          ("skipped", "Skipped"), ("failed", "Failed")):
        items = summary.get(bucket) or []
        if not items:
            continue
        _print_md("\n## {0}\n".format(title))
        for item in items:
            _print_md("- {0} (source: {1}, status: {2})".format(
                item.get("legend"), item.get("source") or "missing", item.get("status") or item.get("reason")
            ))
            for error in item.get("errors") or []:
                _print_md("  - error: {0}".format(error))
    _print_messages("Warnings", summary.get("warnings") or [])
    _print_messages("Errors", summary.get("errors") or [])


def print_audit(audit):
    """Print the audit with clickable element links when pyRevit provides them."""
    _print_md("# Legend audit\n")
    if not audit["rows"]:
        _print_md("No legends made by this tool were found.")
    for row in audit["rows"]:
        _print_md("\n".join([
            "## {0}".format(row["legend_view_name"]),
            "",
            "- Legend: {0}".format(_link(row["legend_view_id"], row["legend_view_name"])),
            "- View: {0}".format(
                "Deleted source {0}".format(row["source_view_id"])
                if row["source_missing"]
                else _link(row["source_view_id"], row["source_view_name"])
            ),
            "- Legend type: {0}".format(row["definition_name"] or row["definition_id"]),
            "- Placed on sheets: {0}".format(", ".join(row["sheets"]) or "No"),
            "- Last update: {0}".format(row.get("updated_utc") or "Unknown"),
            "- Tool version: {0}".format(row.get("tool_version") or "Unknown"),
            "- Visible types: {0}".format(len(row.get("visible_type_ids") or [])),
            "- Types in the legend: {0}".format(len(set(row.get("represented_type_ids") or []))),
            "- Missing from the legend: {0}".format(_id_list(row.get("missing_type_ids"))),
            "- In the legend but no longer visible: {0}".format(_id_list(row.get("obsolete_type_ids"))),
            "- Listed twice: {0}".format(_id_list(row.get("duplicate_type_ids"))),
            "- Overlaps: {0}".format(len(row.get("overlaps") or [])),
        ]))
        _print_messages("Parameter warnings", row.get("missing_parameters") or [])
        _print_messages("Warnings", row.get("warnings") or [])
        if row.get("overlaps"):
            _print_md("Overlapping pairs:")
            for first_id, second_id in row["overlaps"]:
                _print_md("- {0} overlaps {1}".format(first_id, second_id))
    _print_messages("Audit warnings", audit.get("warnings") or [])


def print_library_report(report):
    """Print the result of one library legend create or update."""
    _print_md("\n".join([
        "# {0} legend {1}".format(report.get("category"), report.get("status")),
        "",
        "- Legend: {0}".format(_link(report.get("legend_view_id"), report.get("legend_view_name"))),
        "- Sheet: {0}".format(report.get("sheet") or "none (category legend)"),
        "- Rows: {0}".format(len(report.get("codes") or [])),
        "- Width: {0}".format("{0:g} cm".format(round(report["width_mm"] / 10.0, 1)) if report.get("width_mm") else "-"),
    ]))
    _print_messages("Codes", report.get("codes") or [])
    _print_messages("Warnings", report.get("warnings") or [])
    _print_messages("Errors", report.get("errors") or [])
    _print_messages("Notices", report.get("notices") or [])


def print_library_batch(summary):
    """Print the Update All result for library legends."""
    _print_md("\n".join([
        "# Library legends",
        "",
        "- Updated: {0}".format(len(summary.get("updated") or [])),
        "- Unchanged: {0}".format(len(summary.get("unchanged") or [])),
        "- Skipped: {0}".format(len(summary.get("skipped") or [])),
        "- Failed: {0}".format(len(summary.get("failed") or [])),
    ]))
    for bucket in ("updated", "skipped", "failed"):
        for item in summary.get(bucket) or []:
            _print_md("- {0}: {1} {2}".format(
                item.get("legend"), bucket, item.get("reason") or "; ".join(item.get("errors") or [])
            ))
    _print_messages("Warnings", summary.get("warnings") or [])


def print_library_audit(rows):
    """Print the read-only audit of library legends."""
    _print_md("# Library legend audit\n")
    if not rows:
        _print_md("No library legends were found.")
    for row in rows:
        _print_md("\n".join([
            "## {0}".format(row["legend"]),
            "",
            "- Legend: {0}".format(_link(row.get("legend_view_id"), row["legend"])),
            "- Category: {0}".format(row["category"]),
            "- Source: {0}".format(row.get("source") or "unknown"),
            "- Sheet: {0}".format(row["sheet"]),
            "- Rows: {0}".format(", ".join(row["codes"]) or "None"),
            "- Types no longer in the family: {0}".format(_id_list(row["missing_codes"])),
            "- Type Marks on the sheet that have a family type but are not in the legend: {0}".format(
                _id_list(row["unlisted_marks"])
            ),
            "- Needs update: {0}".format("Yes" if row["outdated"] else "No"),
            "- Problem: {0}".format(row.get("problem") or "None"),
            "- Last update: {0}".format(row.get("updated_utc") or "Unknown"),
        ]))


def alert_error(title, message):
    """Show a short dialog in Revit. Fall back to the output window if no dialog can open."""
    try:
        from dialogs import alert
        alert(message, title=title)
    except Exception:
        _print_md("## {0}\n\n{1}".format(title, message))


def _print_md(markdown):
    output = _output()
    if output is None:
        print(markdown)
        return
    output.print_md(markdown)


def _print_table(rows, headers):
    output = _output()
    if output is None:
        print(headers)
        for row in rows:
            print(row)
        return
    printer = getattr(output, "print_table", None)
    if printer is not None:
        try:
            printer(rows, columns=headers)
            return
        except Exception:
            pass
    _print_md("| " + " | ".join(headers) + " |")
    _print_md("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        _print_md("| " + " | ".join(str(cell) for cell in row) + " |")


def _print_messages(title, messages):
    if not messages:
        return
    _print_md("\n## {0}\n".format(title))
    seen = set()
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        _print_md("- {0}".format(message))


def _excluded_lines(collection):
    counts = {}
    for item in collection.excluded:
        reason = item.get("reason") or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return ["{0}: {1}".format(reason, count) for reason, count in sorted(counts.items())]


def _id_list(values):
    if not values:
        return "None"
    return ", ".join(str(value) for value in values)


def _link(element_id, label):
    text = label or str(element_id)
    if element_id is None:
        return text
    try:
        from version_adapter import make_element_id
        output = _output()
        if output is None:
            return text
        return "{0} ({1})".format(text, output.linkify(make_element_id(element_id)))
    except Exception:
        return text


def _output():
    try:
        from pyrevit import script
        return script.get_output()
    except Exception:
        return None
