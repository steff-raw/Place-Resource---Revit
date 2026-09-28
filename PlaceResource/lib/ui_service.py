# -*- coding: utf-8 -*-
"""Command dialogs. Revit stays unmodified until a dialog returns a commit choice.

All dialogs go through ``dialogs``. ``pyrevit.forms`` is not available under CPython.
"""

import dialogs


def choose_definition(definitions):
    """Ask which legend definition to use. A single definition is confirmed in the summary."""
    if not definitions:
        return None
    if len(definitions) == 1:
        return definitions[0]
    labels = ["{0}  [{1}]".format(item["display_name"], item["id"]) for item in definitions]
    index = dialogs.choose_from_list(
        "Select a legend definition",
        labels,
        prompt="Choose the legend to create or update for this view.",
        button_text="Use this legend",
    )
    if index is None:
        return None
    return definitions[index]


def confirm_plan(source_view, definition, plan, sheet_mode=False):
    """Show the summary and ask whether to commit.

    Returns a dictionary, or None when the user cancels.
    The estimated layout is shown before any transaction starts.
    In sheet mode the source is a sheet, and placing on that sheet is the first option.
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
    source_views = collection.view_info.get("source_views")
    if source_views:
        summary.insert(1, "Views on the sheet: {0}".format(", ".join(source_views)))
    if collection.warnings:
        summary.append("Warnings before commit: {0}. Details are in the output window.".format(
            len(collection.warnings)
        ))
    preview = ("preview", "Preview only", "Leave the model unchanged. The output window keeps the preview.")
    if sheet_mode:
        options = [
            ("apply_and_place", "Create or update, and place it on this sheet",
             "If the legend is already on this sheet, its position is kept."),
            ("apply", "Create or update only"),
            preview,
        ]
    else:
        options = [
            ("apply", "Create or update the legend"),
            ("apply_and_place", "Create or update, then place it on a sheet"),
            preview,
        ]
    choice = dialogs.choose_command(
        "Create / Update View Legend",
        "Create or update the legend for '{0}'?".format(source_view.Name),
        options,
        content="\n".join(summary),
    )
    if choice is None:
        return None
    return {
        "apply_changes": choice in ("apply", "apply_and_place"),
        "place_on_sheet": choice == "apply_and_place",
    }


def confirm_delete(type_labels):
    """Ask before obsolete managed entries are removed."""
    preview = "\n".join(type_labels[:20])
    extra = ""
    if len(type_labels) > 20:
        extra = "\n... and {0} more".format(len(type_labels) - 20)
    return dialogs.ask_yes_no(
        "Remove obsolete legend entries",
        "Remove {0} legend entr{1} that are no longer visible in the source view?".format(
            len(type_labels), "y" if len(type_labels) == 1 else "ies"
        ),
        content="{0}{1}\n\nOnly tool-managed entries are removed. Manual notes stay.".format(preview, extra),
        yes_label="Remove them",
        no_label="Keep them",
    )


def choose_named_item(title, items, label_for):
    """Pick one object from a list. ``label_for`` receives the object."""
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    labels = [label_for(item) for item in items]
    index = dialogs.choose_from_list(title, labels)
    if index is None:
        return None
    return items[index]


def pick_sheet_point(uidoc):
    """Let the user pick a sheet point. Returns None if the pick is cancelled."""
    from Autodesk.Revit.Exceptions import OperationCanceledException
    try:
        return uidoc.Selection.PickPoint("Pick the legend anchor on the sheet")
    except OperationCanceledException:
        # pythonnet may wrap the Revit exception differently.
        return None
    except Exception as ex:
        if "cancel" in str(ex).lower():
            return None
        raise


SETTINGS_ACTIONS = (
    "Validate configuration",
    "Choose configuration file",
    "Use the built-in configuration",
    "Open configuration file",
)


def choose_settings_action():
    """Return the settings command the user picked, or None."""
    return dialogs.choose_command(
        "Legend Settings",
        "Legend settings",
        [
            (SETTINGS_ACTIONS[0], SETTINGS_ACTIONS[0], "Check the current JSON file and list its legends."),
            (SETTINGS_ACTIONS[1], SETTINGS_ACTIONS[1], "Use a project-specific JSON file from now on."),
            (SETTINGS_ACTIONS[2], SETTINGS_ACTIONS[2], "Go back to config/legends.json."),
            (SETTINGS_ACTIONS[3], SETTINGS_ACTIONS[3], "Open the current JSON file in the default editor."),
        ],
        footer="Office styles and spacing are stored in JSON, not in the Python code.",
    )


def pick_settings_file():
    """Return a JSON path chosen by the user."""
    return dialogs.pick_file("Select the legend settings file")
