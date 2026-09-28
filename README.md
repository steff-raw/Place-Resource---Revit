# Place Resource: View-Based Legends

pyRevit panel that builds legends from the types visible in the active view.

## Repository layout

```
Legends.panel/        pyRevit panel. Copy into any .tab folder, e.g. MyTool.extension/Bham-Tools.Tab/
PlaceResource/
    lib/              Python modules used by the buttons (required)
    config/           legends.json, parameter_aliases.json, schema.json (required)
    tests/            unit tests, run outside Revit (not deployed)
.claude/skills/       Claude Code skills (pyrevit, revit-api). Not deployed
```

## Test status

No Revit version and no pyRevit version have been tested with this tool.

The code targets the pyRevit CPython 3 engine and the public Revit API. Do not treat any version as supported until the manual checklist below has been run in that version and the result has been recorded here.

| Revit | pyRevit | Engine | Result |
| --- | --- | --- | --- |
| Not recorded | Not recorded | CPython 3 (required) | Not tested |

Every button script starts with `#! python3`, so pyRevit runs it in CPython 3. IronPython is not supported.

## What it does

The **Legends** panel (ribbon title **Place Resources**) works from a plan, section, or elevation. It collects the wall types that are actually visible, then creates or updates a legend that contains only those types.

Walls are the first category with explicit rules. Doors use a generic category adapter so a door legend can be configured, but that path has not been run inside Revit. Windows, floors, ceilings, furniture, and generic models can be added by copying a legend definition and pointing `category` at the matching `OST_` name listed in `lib/category_adapter.py`.

Office names, text styles, spacing, and parameters live in `config/legends.json` and `config/parameter_aliases.json`. They are not hard-coded in Python.

## Install

1. Install pyRevit. The CPython 3 engine must be available.
2. Copy `Legends.panel` into an existing `.tab` folder, for example `MyTool.extension\Bham-Tools.Tab\`.
3. Copy the `PlaceResource` folder (`lib` and `config`; `tests` is optional) to `Documents\Gensler\Python\PlaceResource`. `config` must sit next to `lib`.
4. Reload pyRevit.
5. Prepare the template legends described below.
6. Open **Legend Settings** and confirm the JSON file validates. If the project uses different text styles, edit `styles` in the JSON file. Do not edit the Python to change them.
7. Paste shared-parameter GUIDs for Acoustic Rating into `parameter_aliases.json` when the office uses a shared parameter.

Each button looks for a folder that contains `lib/legend_service.py`, in this order:

1. The folder named by the `PLACE_RESOURCE_HOME` environment variable.
2. `PlaceResource` next to `Legends.panel` (this repository's layout).
3. `Documents\Gensler\Python\PlaceResource` under OneDrive (`%OneDriveCommercial%`, then `%OneDrive%`), then under the user profile.

User settings, the settings pointer file, and any JSON registry fallback are written under that folder's `config`.

Shift-click **Legend Settings** to pick a different JSON file for the project. The chosen path is stored in `config/user_settings_path.txt`.

## Prepare a template legend

The public Revit API cannot create a legend view from nothing, and it cannot create a legend component from nothing. The tool duplicates a real legend view and copies a seed component that already exists in that view.

For the wall legend:

1. In the project, create a normal legend view named exactly `_TEMPLATE - WALL LEGEND`. This is not a Revit view template.
2. Place one wall legend component in it.
3. Set that component's view direction to Section and its host length to 1200 mm.
4. Leave the legend scale at 1:20 and the detail level at Fine, or let the tool set those on the duplicate when the legend is first created.
5. Do not add a second legend component. Notes in the template are copied into new legends and then left untouched, so keep the template limited to the seed.
6. Repeat the same steps for `_TEMPLATE - FIRE WALL LEGEND`, `_TEMPLATE - ACOUSTIC WALL LEGEND`, and `_TEMPLATE - DOOR LEGEND` if those definitions are used. A door seed must be a door legend component.

The tool never modifies the template view. It duplicates it, renames the duplicate, and works on the duplicate.

## User workflow

### Create / Update View Legend

1. Open a floor plan, ceiling plan, section, or elevation, **or a sheet**.
2. Run **Place Resources → Create / Update View Legend**.
3. Choose Wall Type Legend, Fire-Rated Wall Legend, Acoustic Wall Legend, or Door Type Legend.
4. Read the preview in the output window. It lists visible instances, unique types, exclusions, and an estimated size taken from the JSON spacing.
5. Pick **Create or update the legend**, **Create or update, then place it on a sheet**, or **Preview only** to leave the model unchanged.
6. If types disappeared from the view, confirm or decline removal. Declining keeps those managed entries. Manual notes are never deleted.
7. If you picked the sheet option, choose the sheet and pick a point.

#### From a sheet

When the active view is a sheet, the sheet is the source:

- Types are collected from every view placed on the sheet whose type is in the definition's `source_view_types` (plans, sections, elevations). Legends, schedules and drafting views are skipped.
- A wall that shows in more than one of those views counts once.
- The first option in the dialog creates or updates the combined legend and places it on this sheet. If it is already on the sheet, its position is kept.
- The legend is named from the sheet number and name, for example `WALL LEGEND - A101 - Plans`, and is linked to the sheet. Adding or removing views on the sheet changes the legend on the next update.

The command shows the source view, definition, instance count, unique type count, any existing generated legend, and the update mode before it commits.

### Place Legend on Sheet

- From a model view, the command finds sheets that already contain that view. If several exist, you pick one. If none exist, you pick any sheet.
- From a sheet, you pick **All views on this sheet** (one combined legend) or one model viewport. The tool finds or creates the matching legend and places it on the active sheet.
- Pick a point, or set `sheet_placement.mode` to `configured_point` and supply `anchor_x_mm` / `anchor_y_mm`.
- A second viewport on the same sheet is refused. The existing viewport is not moved.
- Legends may be placed on more than one sheet. Later updates restore the viewport centre when `preserve_viewport_position` is true.
- If the sheet is not already active, the command activates it for the pick and then returns to the previous view.

### Update All Generated Legends

Scans legends marked by this tool, skips a legend whose stored content hash still matches, skips a deleted source view and reports it, and preserves viewport positions. One legend failing does not roll back the legends that already succeeded.

### Audit Generated Legends

Read-only. The output lists the source view, generated legend, definition, visible types, represented types, missing types, obsolete types, missing required parameters, duplicate entries, overlaps, deleted source views, sheet placement, and the last update. Element ids are linkified in the pyRevit output when that output supports it.

### Settings

Validates the JSON, chooses another settings file, returns to the built-in file, or opens the file. Invalid text styles are reported when a legend command runs, before any transaction starts, and the message lists text types that do exist.

## How a legend is matched to a view

The legend name is only a label. The relationship is stored on the legend view with Extensible Storage:

- source view id and UniqueId
- legend definition id
- UTC time of the last update
- tool version
- content hash
- settings schema version

Each generated component, label, heading, border, and optional layer object stores its own entity: definition id, source view id, type id, role, and tool version. The updater deletes or moves an element only when that entity is present.

If Extensible Storage cannot be written, the tool writes `config/registries/<document-key>.json` and warns that this file does not travel with the model. It does not create a project parameter. When `output_identity_parameter` already exists on views and is writable, the tool also writes `definitionId|sourceViewId` there.

## Visible elements

Collection uses `FilteredElementCollector(document, sourceView.Id)` filtered to the category and to elements that are not types. That collector already applies the view phase, phase filter, design option visibility, category visibility, hiding view filters, permanent element hide, closed worksets, and the crop region.

These are not a second filter:

- Detail level and view discipline are reported and do not, by themselves, remove walls.
- The design option currently active in the UI is ignored. The view's own design-option visibility is what matters.
- Temporary hide/isolate is applied when this Revit build exposes a temporary-hide list. If it does not, the report says so and the collector result is used.
- Parts are not wall types. When the view shows parts only, the original wall is excluded unless `when_parts_replace_original` is true.
- Linked walls are off by default. When enabled, they are read from the link document and kept only when the host model has a type with the same family name and type name. Host view filters are not fully applied to link elements, and the report says so.
- Curtain walls, stacked walls, stacked-wall members, in-place walls, demolished walls, and links are excluded unless the JSON include flags say otherwise.
- Other categories take only `in_place`, `linked_models` (required), and `demolished`. Wall-only flags on a non-wall definition fail validation.

A type that is loaded but unused in the view is not listed. `unused_loaded_types` is `exclude`.

## Parameters

For each configured key the resolver tries:

1. The built-in parameter named in `parameter_aliases.json`.
2. The shared parameter GUID.
3. Each exact project parameter name in the alias.
4. The label or alias default.

A required parameter that is still missing is listed as a warning. An optional miss is left as the configured blank token and is not a warning. Empty strings count as missing so the next fallback can run.

Width is stored by Revit in decimal feet and formatted with `format: millimetres`. Compound structure, materials, and layer thicknesses are read from `WallType.GetCompoundStructure()` and included on the type record. They are not drawn unless `representation.layer_reference_planes` is true.

## Layout

Coordinates in the JSON are millimetres. The layout engine converts them to Revit decimal feet (millimetres / 304.8).

The commit uses two passes:

1. Create or update components and text, regenerate, and measure bounding boxes.
2. Compute final coordinates, move each managed element so its box top-left hits that coordinate, regenerate, and report any remaining overlap.

Rows grow when `auto_size_rows` is true and wrapped text is taller than `row_height_mm`. Columns grow when measured content is wider than the configured width, and the report says which label was expanded. Origins support `top_left`, `top_right`, `bottom_left`, and `bottom_right`. Natural sort orders W1, W2, W10.

The dialog's size is an estimate from the JSON, calculated before the transaction. Measured boxes exist only after Revit creates the elements, so the measured pass happens after you confirm. A modal dialog is not opened in the middle of a transaction.

## What the tool will not do

- Modify a model wall, door, floor, or other model instance.
- Change a type's parameters.
- Delete annotation that this tool did not mark.
- Delete a legend that is not tool-managed.
- Change the source view's filters, visibility, phase, or design option.
- Replace a legend component with detail lines unless `fallback_detail_lines` is true.
- Suppress Revit warnings. Warnings are copied into the report and left for Revit to handle.

A failed create or update rolls back the whole transaction group. The completion report lists created or updated state, source view, instance count, unique types, entries added, updated, and removed, warnings, and errors.

## Known Revit API limits

- There is no public API that creates a legend view. The tool duplicates the named template legend, preferring `WithDetailing` so the seed is copied.
- There is no public `LegendComponent.Create`. `LegendComponentService` copies the seed with `ElementTransformUtils.CopyElement` and sets `BuiltInParameter.LEGEND_COMPONENT`. If Revit returns false or the value does not read back, the command stops and rolls back. It does not draw a fake wall.
- `LEGEND_COMPONENT_VIEW` has no documented integer enum. The tool does not write a guessed integer. It keeps the seed direction and warns when the seed text does not match `representation.view_direction`.
- Host length is written only when a writable length parameter exists (`LEGEND_COMPONENT_LENGTH`, or a parameter named exactly `Length` or `Host Length`). Otherwise the seed length is kept and the report says the configured millimetre length was not applied.
- Layer reference planes are optional and off by default. They are created only when the component bounding box matches the compound-structure width within 5 mm, on the axis that matches. A failure rolls back only that subtransaction. `fallback_detail_lines` then draws drafting lines and warns that they are disconnected. Leave both flags false until this has been checked in the target Revit version. Reference planes are view-specific in current API docs; confirm they do not appear as model datums before enabling the flag on a live project.
- A view-scoped collector is not a pixel-perfect render. Underlays, temporary hide on builds that hide the element list, and linked models can differ from what is on screen. Those differences are written into the command notices.

## Modules

| Module | Role |
| --- | --- |
| `collectors.py` | View-scoped collection and unique types |
| `category_adapter.py` | Wall rules and the generic adapter for other categories |
| `configuration.py` | JSON load, schema 1.0 checks, view names |
| `parameter_service.py` | Built-in, GUID, name, and default resolution |
| `legend_service.py` | Create, update, and project-wide update |
| `legend_component_service.py` | Seed copy, type assignment, text, optional layer graphics |
| `layout_engine.py` | Sorting and the pure two-pass coordinate math |
| `placement_service.py` | Sheet discovery and viewport creation |
| `audit_service.py` | Read-only comparison |
| `identity.py` | Extensible Storage and the JSON fallback |
| `validation.py` | Document and source-view checks |
| `version_adapter.py` | ElementId, built-in parameter lookup, host version |
| `units.py` | Millimetres to decimal feet |
| `transactions.py` | Transaction groups and rollback |
| `reporting.py` | Output window text and links |
| `ui_service.py` | Definition, commit, and settings dialogs |
| `dialogs.py` | CPython-safe dialogs: Revit TaskDialog, a filterable Windows Forms list, file picker. `pyrevit.forms` is not used |
| `logging_service.py` | pyRevit logger, or the standard logger in tests |
| `errors.py` | Actionable exceptions |

## Phased plan

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Validate the view, collect visible walls, report without editing | Implemented, not run in Revit |
| 2 | Load JSON, duplicate the template, store identity | Implemented, not run in Revit |
| 3 | Copy the seed, assign types, label, two-pass align | Implemented, not run in Revit |
| 4 | Add, remove, and relabel managed entries; keep manual notes and viewport centres | Implemented, not run in Revit |
| 5 | Place on a sheet, update all, audit | Implemented, not run in Revit |
| 6 | Other categories through JSON and adapters | Generic adapter implemented for doors, windows, floors, ceilings, furniture, generic models, columns, roofs, and stairs. Only the door definition is in the sample file. None of these categories have been run in Revit |

After a Revit test, record the version in the table at the top. Do not mark a phase supported before that.

## Manual test checklist

Run these on a copy of a project. Record the Revit and pyRevit versions in the table above.

- [ ] View with one wall type.
- [ ] View with several wall types.
- [ ] Wall type added to the view, then update.
- [ ] Wall type removed from the view, then update, including declining the delete prompt.
- [ ] Wall hidden by element.
- [ ] Wall hidden by category.
- [ ] Wall removed by a view filter.
- [ ] Wall in a different phase, including a demolished wall when the view still shows demolition.
- [ ] Wall in a design option that the view does not show.
- [ ] Curtain wall excluded by default, then included from JSON.
- [ ] Stacked wall excluded, and its members excluded.
- [ ] Linked wall excluded by default. With links enabled, a matching host type is used and an unmatched link type is warned.
- [ ] Two types with the same Type Mark both appear, and the report warns.
- [ ] Missing Fire Rating on an optional label does not fail the command.
- [ ] Missing Fire Rating on the fire legend, where the label is required, produces a warning.
- [ ] A very long Type Name wraps and the row grows.
- [ ] A manual text note in the legend survives an update and is not moved.
- [ ] Legend already on a sheet keeps its viewport centre after an update.
- [ ] Source view on two sheets asks which sheet to use.
- [ ] Deleted source view is skipped by Update All and reported by Audit.
- [ ] Missing template legend stops before changing the model.
- [ ] Template with no seed component fails clearly.
- [ ] JSON text style that does not exist fails before a transaction.
- [ ] A forced transaction failure rolls the new legend back. Confirm with Undo that the model matches the pre-command state.
- [ ] Seed view direction is kept when it already says Section, and a mismatch produces a warning without writing an integer.
- [ ] `layer_reference_planes` left false creates no reference planes. A separate test model is used before turning it on.

## Troubleshooting

| Message | What to do |
| --- | --- |
| Template legend was not found | Create a real legend view with the exact `template_legend_name`. Do not create a view template. |
| No seed legend component | Place one legend component in that template. |
| Seed category does not match | The seed must be a wall component for a wall definition, or a door component for the door definition. |
| Revit rejected the legend component type change | The version refused `LEGEND_COMPONENT`. The command rolls back. Do not expect detail lines unless you set `fallback_detail_lines`. |
| Text note type was not found | Change `styles.text_note_type` to a type listed in the error, or create the named type. |
| View parameter was not found | Expected unless the project already has `GeneratedLegendSourceViewId`. Identity still uses Extensible Storage. |
| Host length was not applied | Set the length on the seed. The API did not expose a writable length parameter. |
| View direction was not changed | Set the direction on the seed. The tool does not guess the integer. |
| Linked type has no matching type | Load or create the same family and type name in the host, or leave `linked_models` false. |
| Settings schema_version is not supported | Keep `schema_version` at `1.0` until a migration is added. |
| Extensible Storage was unavailable | The local registry under `config/registries` was used. Do not rely on it outside this machine. |

## Developer tests

From `PlaceResource`:

```bash
python -m unittest discover -s tests -v
```

These tests do not load Revit. They cover settings validation, natural sort, layout coordinates, and parameter fallback.
