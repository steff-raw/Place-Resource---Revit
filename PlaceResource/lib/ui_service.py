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
    "Choose legend text style",
    "Validate configuration",
    "Choose configuration file",
    "Use the built-in configuration",
    "Show configuration file location",
)


SETTINGS_DETAILS = (
    "text note type for legend headings and type-legend text; saved in this Revit model",
    "check the settings file and list its legend definitions",
    "use a project-specific settings file (JSON)",
    "go back to the settings file shipped with the tool",
    "show where the settings file is, to open it in your editor",
)


def choose_settings_action(doc=None):
    """Return the settings command the user picked, or None."""
    prompt = "Choose a setting, then press Open. The text style is saved in this Revit model."
    if doc is not None:
        import project_settings
        try:
            prompt = "{0}\n{1}".format(prompt, project_settings.describe(project_settings.read(doc)))
        except Exception:
            pass
    index = dialogs.choose_from_list(
        "Legend Settings",
        list(SETTINGS_ACTIONS),
        prompt=prompt,
        button_text="Open",
        details=list(SETTINGS_DETAILS),
    )
    return None if index is None else SETTINGS_ACTIONS[index]


def choose_text_type(doc, reason=None):
    """Pick the legend text style from the project's text note types and save it in the model.

    Returns the chosen name, or None when cancelled.
    """
    from legend_component_service import text_type_names
    import project_settings
    names = text_type_names(doc)
    if not names:
        dialogs.alert("This project has no text note types.", title="Legend text style")
        return None
    current = project_settings.read(doc)["text_type"]
    labels = ["{0}{1}".format(name, "   (current)" if name == current else "") for name in names]
    prompt = "Choose the text style for text the tool writes (legend headings and type-legend labels)."
    if reason:
        prompt = "{0} {1}".format(reason, prompt)
    index = dialogs.choose_from_list(
        "Legend text style", labels, prompt=prompt, button_text="Use this style",
        selected_index=names.index(current) if current in names else 0,
    )
    if index is None:
        return None
    data = project_settings.read(doc)
    data["text_type"] = names[index]
    project_settings.save(doc, data, "Place Resource: legend text style")
    return names[index]


def ensure_text_style(doc, fallback_names):
    """Make sure generated legend text has a text type before anything changes.

    When neither the saved style nor the settings-file names exist, the picker opens.
    Returns True to continue, False when the user cancelled.
    """
    from legend_component_service import text_types_resolve
    names = sorted(set(name for name in fallback_names if name))
    if text_types_resolve(doc, names):
        return True
    return choose_text_type(
        doc,
        reason="The text style in the settings file ({0}) is not in this project.".format(", ".join(names)),
    ) is not None


def pick_settings_file():
    """Return a JSON path chosen by the user."""
    return dialogs.pick_file("Select the legend settings file")
