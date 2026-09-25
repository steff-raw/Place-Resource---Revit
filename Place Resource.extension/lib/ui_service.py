# -*- coding: utf-8 -*-
"""Command dialogs. Revit stays unmodified until a dialog returns a commit choice."""

from logging_service import get_logger

LOGGER = get_logger("ui_service")


def choose_definition(definitions):
    """Ask which legend definition to use. A single definition is confirmed in the summary."""
    if not definitions:
        return None
    if len(definitions) == 1:
        return definitions[0]
    from pyrevit import forms
    labels = ["{0}  [{1}]".format(item["display_name"], item["id"]) for item in definitions]
    selected = forms.SelectFromList.show(
        labels,
        title="Select a legend definition",
        button_name="Use this legend",
        multiselect=False,
    )
    if not selected:
        return None
    return definitions[labels.index(selected)]


def confirm_plan(source_view, definition, plan):
    """Show the summary and ask whether to commit.

    Returns a dictionary, or None when the user cancels.
    The estimated layout is shown before any transaction starts.
    """
    collection = plan["collection"]
    existing = plan["existing_name"] or "None — a new legend will be duplicated from the template"
    block = plan["estimate"]["block"]
    summary = [
        "Source view: {0} ({1})".format(source_view.Name, collection.view_info.get("view_type") or ""),
        "Legend definition: {0}".format(definition["display_name"]),
        "Visible instances: {0}".format(collection.instance_count),
        "Unique types: {0}".format(collection.unique_type_count),
        "Existing generated legend: {0}".format(existing),
        "Update mode: {0}".format(plan["mode"]),
        "Entries to add: {0}".format(len(plan["to_add"])),
        "Entries no longer visible: {0}".format(len(plan["to_remove"])),
        "Estimated size: {0:.0f} x {1:.0f} mm (settings preview, not measured boxes)".format(
            block["width"] * 304.8, block["height"] * 304.8
        ),
    ]
    if collection.warnings:
        summary.append("Warnings before commit: {0}. Details are in the output window.".format(
            len(collection.warnings)
        ))
    try:
        return _flex_confirm(summary)
    except Exception as ex:
        LOGGER.warning("The detailed dialog was unavailable (%s). A yes/no prompt was used.", ex)
        return _alert_confirm(summary)


def confirm_delete(type_labels):
    """Ask before obsolete managed entries are removed."""
    from pyrevit import forms
    preview = "\n".join(type_labels[:20])
    extra = ""
    if len(type_labels) > 20:
        extra = "\n... and {0} more".format(len(type_labels) - 20)
    return bool(forms.alert(
        "Remove {0} legend entr{1} that are no longer visible in the source view?\n\n{2}{3}\n\n"
        "Only tool-managed entries are removed. Manual notes stay.".format(
            len(type_labels),
            "y" if len(type_labels) == 1 else "ies",
            preview,
            extra,
        ),
        title="Remove obsolete legend entries",
        ok=False,
        yes=True,
        no=True,
    ))


def choose_named_item(title, items, label_for):
    """Pick one object from a list. ``label_for`` receives the object."""
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    from pyrevit import forms
    labels = [label_for(item) for item in items]
    selected = forms.SelectFromList.show(
        labels,
        title=title,
        button_name="Select",
        multiselect=False,
    )
    if not selected:
        return None
    return items[labels.index(selected)]


def pick_sheet_point(uidoc):
    """Let the user pick a sheet point. Returns None if the pick is cancelled."""
    from pyrevit import DB
    try:
        return uidoc.Selection.PickPoint("Pick the legend anchor on the sheet")
    except DB.OperationCanceledException:
        # pythonnet may wrap the Revit exception differently.
        return None
    except Exception as ex:
        if "cancel" in str(ex).lower():
            return None
        raise


def choose_settings_action():
    """Return the settings command the user picked."""
    from pyrevit import forms
    return forms.CommandSwitchWindow.show(
        [
            "Validate configuration",
            "Choose configuration file",
            "Use the built-in configuration",
            "Open configuration file",
        ],
        message="Legend settings are stored in JSON. Python code does not contain office styles or spacing.",
    )


def pick_settings_file():
    """Return a JSON path chosen by the user."""
    from pyrevit import forms
    return forms.pick_file(file_ext="json", title="Select the legend settings file")


def _flex_confirm(summary_lines):
    from pyrevit import forms
    components = [forms.Label(line) for line in summary_lines]
    components.extend([
        forms.Separator(),
        forms.CheckBox("apply_changes", "Create or update the legend", default=True),
        forms.CheckBox("place_on_sheet", "Place the legend on a sheet after updating", default=False),
        forms.Separator(),
        forms.Button("Continue"),
    ])
    form = forms.FlexForm("Create / Update View Legend", components, width=560)
    accepted = form.show()
    if not accepted:
        return None
    values = getattr(form, "values", None) or {}
    if not values:
        return None
    return {
        "apply_changes": bool(values.get("apply_changes", True)),
        "place_on_sheet": bool(values.get("place_on_sheet", False)),
    }


def _alert_confirm(summary_lines):
    from pyrevit import forms
    accepted = forms.alert(
        "\n".join(summary_lines),
        title="Create / Update View Legend",
        ok=False,
        yes=True,
        no=True,
    )
    if not accepted:
        return None
    return {"apply_changes": True, "place_on_sheet": False}
