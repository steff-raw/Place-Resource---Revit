# Place Resource: Sheet Legends

pyRevit panel that builds legends on sheets from symbol families, based on the Type Marks shown in the sheet's views.

## How it works

### In one line

The walls (or doors, floors, ceilings) shown on a sheet carry Type Marks. The tool finds the matching types in your symbol family and draws a bordered legend on that sheet: graphic on the left, description on the right.

### Quick start

1. **Make the symbol family** (once): one type per Type Mark, e.g. `IWS-105`, with `Legend_Description` filled in. See [The symbol family](#the-symbol-family-made-by-hand-once-per-category).
2. **Load it** into the project.
3. **Legend Setup** (once per project): pick the heading font, the description font and the family for each category. Press Done.
4. **Open a sheet > Place Legend on Sheet:** tick Walls, draw a box where the legend goes, choose Type Mark on/off, type the headings.
5. **After design changes > Update All Generated Legends:** every legend is redrawn in place.

### What happens behind each step

| Step | What the tool does |
|---|---|
| Legend Setup | Saves the fonts and the family for each category in the model (Extensible Storage). Nothing is drawn. |
| Reading the sheet | Collects the elements of the category visible in each plan, section, elevation and detail view on the sheet (linked models too), reads their Type Marks. |
| Matching | Compares each Type Mark with the family type names and `Legend_TypeMark`, ignoring case, spaces and dash style. Only matching types become rows. |
| Making the legend view | Copies an existing legend view (Revit cannot create one from nothing), names it `<Category> LEGEND - <sheet number>`, sets the scale. |
| Drawing | Places one symbol per row, sets `Legend_TypeMark_Visibility` and `Text_Visibility`, writes the headings and wrapped descriptions as text notes, and draws the table lines. |
| Sizing | The graphic column fits the widest symbol. The description column takes the rest of the width you chose; text wraps to it. Each row is as tall as its symbol or its text. |
| Placing | Puts the legend on the sheet at the box corner (or the point you pick) with the `No Title` viewport type. |
| Remembering | Stores on the legend: category, sheet, rows, width, headings, Type Mark choice. Stores in the model: the last headings per category, for next time. |
| Update All | Finds the tool's legends by that stored data or by name, deletes everything inside each one, redraws it with the current Type Marks and family, then moves the viewport back so its top-left corner is where it was. |

### Rules it follows

- Only legends made by the tool are changed. Model elements are never touched.
- Every command is one undo step. If something fails, the whole change is undone.
- Hand edits inside a tool legend are replaced on the next update.
- Nothing leaves the computer: no internet, no other programs.

## Repository layout

```
Legends.panel/        pyRevit panel. Copy into any .tab folder, e.g. MyTool.extension/Bham-Tools.Tab/
PlaceResource/
    lib/              Python modules used by the buttons (required)
    config/           library_legends.json and other settings (required)
    tests/            unit tests, run outside Revit (not deployed)
.claude/skills/       Claude Code skills. Not deployed
```

## Security

The tool works fully offline. It opens no network connection, contains no URLs, starts no other program, and writes only to `PlaceResource/config`, `PlaceResource/logs/last_run.txt` and Extensible Storage in the model. Check before each release:

```bash
python .claude/skills/offline-security/scripts/check_offline.py
```

Rules: `.claude/skills/offline-security/SKILL.md`.

## Install

1. pyRevit with the CPython 3 engine. Every script starts with `#! python3`.
2. Copy `Legends.panel` into a `.tab` folder, e.g. `MyTool.extension\Bham-Tools.Tab\`.
3. Copy `PlaceResource\lib` and `PlaceResource\config` to `Documents\Gensler\Python\PlaceResource`. `config` sits next to `lib`.
4. Restart Revit.

The buttons look for `lib` in: `PLACE_RESOURCE_HOME`, then `PlaceResource` next to `Legends.panel`, then `Documents\Gensler\Python\PlaceResource` under OneDrive or the user profile.

### Updating the code

| Replaced | Then |
|---|---|
| Files in `lib` or `config`, or a `script.py` | Click the button again. No Reload. |
| A `bundle.yaml`, or buttons added or removed | Restart Revit. Do not use pyRevit Reload: on Revit 2025 it breaks Python 3 tools until Revit restarts. |

## The symbol family (made by hand, once per category)

- **Family:** Generic Annotation or Detail Item. Any name; you pick it in Legend Setup.
- **One type per Type Mark:** type name = Type Mark, e.g. `IWS-105`.
- **Parameters** (names can be changed in `library_legends.json`):

  | Parameter | Kind | What the tool does |
  |---|---|---|
  | `Legend_Description` | type, text | Writes it as wrapped text in the description column |
  | `Legend_TypeMark` | type, label above the graphic | Also matched against the wall Type Marks |
  | `Legend_TypeMark_Visibility` | instance, Yes/No | Set once per legend from your answer |
  | `Text_Visibility` | instance, Yes/No | Always set to No (the tool writes the text) |

- **Graphic:** draw the hatch or swatch per type any way you like.

## Buttons

### Legend Setup

Settings for this model only:

- **Heading font:** text type for the main and column headings (uses the description font when not set).
- **Description font:** text type for the descriptions.
- **One row per category** (Walls, Fire Strategy, ...): pick its symbol family from the Generic Annotation and Detail Item families loaded in the model.

- **Window:** fonts on top, a separator, then one row per category. Green = family loaded (`Walls - Legend Symbol and text`), red = not loaded (`Fire Strategy - Not loaded`).
- Pick a row and press Change; press Done to finish. The window says how many are still to set.
- **Saved in the model** (Extensible Storage on a DataStorage element), so Sync with Central sends it to central and everyone on the project gets the same setup. In a shared model the settings element is checked out when you change it; if someone else has it, the tool says who.

### Place Legend on Sheet

1. Uses the open sheet, or asks which sheet.
2. Tick the categories. Ticked at start: legends the sheet already has.
3. For each category:
   - **Rows:** Walls, Floors, Ceilings and Doors use the family types matching a Type Mark in the sheet's plans, sections, elevations and detail views (linked models included). Other categories use every type of the family. No tick list.
   - **Width:** draw a box on the sheet (sets width and top-left position) or type it in cm.
   - **Type Mark** above each symbol: show or hide.
   - **Headings:** main heading, graphic column and description column, e.g. PARTITION TYPES LEGEND / SRS CODE / DESCRIPTION. Prefilled with the last values for that category.
4. The legend `<Category> LEGEND - <sheet number>` is drawn as a bordered table and placed with the `No Title` viewport type.

Matching ignores case, spaces and dash style (`IWS - 105` = `IWS-105`). When nothing matches, the message lists the views checked, the Type Marks found and the family types.

A new legend view is copied from `_TEMPLATE - LIBRARY LEGEND` if it exists, otherwise from any legend view in the model. A model with no legend view at all needs one made by hand once (View > Legends > Legend).

### Update All Generated Legends

- Finds every legend this tool made: by the data stored on it, or by its name (`<Category> LEGEND - <sheet number>`).
- Clears and redraws each one, so anything changed by hand inside it (symbols, text, lines) is replaced.
- Rows follow the Type Marks now on the sheet.
- Keeps each legend's width, headings and Type Mark choice, and each viewport's top-left corner. Only the bottom edge moves if the row count changes.

Any legend named like `Walls LEGEND - A-101` is treated as the tool's, so don't use that naming for legends made by hand.

### Audit Generated Legends

Read-only list of the tool's legends: category, sheet, rows, missing family types, and Type Marks on the sheet that have a family type but are not in the legend.

## library_legends.json

Shared `defaults`, then one entry per category:

- `family_name` (used until a family is picked in Legend Setup), `description_parameter`, `type_mark_parameter`, `type_mark_visibility_parameter`, `text_visibility_parameter`, `show_type_mark`
- `revit_category` (`OST_Walls` etc., `null` for zone categories) and `source_view_types`
- `sheet_output_name_pattern` (default `{category} LEGEND - {sheet_number}`), `scale`, `viewport_type_name` (default `No Title`)
- `headings` defaults, `styles` (`heading_text_type`, `text_type`, `border_line_style`), `layout` (`width_mm`, `cell_padding_mm`, `text_pattern`)

## Not yet confirmed in Revit

- Placing annotation symbols in a legend with `NewFamilyInstance`.
- `Selection.PickBox` on a sheet and keeping the viewport corner with `SetBoxCenter`.
- Collecting linked elements with `FilteredElementCollector(doc, viewId, linkId)` (Revit 2024+).

## Manual test checklist

- [ ] Legend Setup: set both fonts and the Walls family; reopen and see them kept, and "All set" shown.
- [ ] Place Legend on Sheet on a sheet with walls IWS-101/102/105: only those three rows, bordered table, headings, no viewport title.
- [ ] Draw a 12 cm box: text wraps inside 12 cm, legend top-left at the box corner.
- [ ] Headings typed once come back prefilled for the next Walls legend.
- [ ] Move a symbol and delete a line in the legend, run Update All: the legend is redrawn, same width, same top-left.
- [ ] Add a wall type to the sheet's view, run Update All: a row is added, the legend grows downward only.
- [ ] Undo after any command removes the whole change.

## Troubleshooting

| Message | Fix |
|---|---|
| No walls on the sheet match | Read the lists in the message: no views checked means the view type is not in `source_view_types`; no Type Marks means the walls have none. |
| Viewport type 'No Title' is not in this model | Load or make that viewport type, or change `viewport_type_name`. |
| This model has no legend views | View > Legends > Legend, once per model. |
| Revit closes during a command | Send `Documents\Gensler\Python\PlaceResource\logs\last_run.txt`: its last line is the step that was running. |

## Developer tests

```bash
cd PlaceResource
python -m unittest discover -s tests
```
