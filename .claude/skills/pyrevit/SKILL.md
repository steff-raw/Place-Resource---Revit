---
name: pyrevit
description: Conventions, Revit API pitfalls and a review checklist for the Place Resource pyRevit extension. Use when writing, reviewing or debugging any pushbutton script, lib/ service, bundle.yaml or config JSON in Legends.panel or PlaceResource, or when a question involves pyRevit engines (IronPython vs CPython), Revit API calls, transactions, legends, Extensible Storage or pyRevit forms.
---

# pyRevit extension skill

Nothing here has been confirmed inside Revit. Never state a Revit or pyRevit version as supported unless the README test table records it.

## Repo layout

```
Legends.panel/                     deployed into a .tab folder (e.g. MyTool.extension/Bham-Tools.Tab/)
  bundle.yaml                      title "Place Resources", button order
  <Name>.pushbutton/
      script.py      thin command: validate -> plan -> confirm -> service call -> report
      bundle.yaml    title, tooltip, author, context (doc-project)
      icon.png       32x32 (add icon.dark.png for dark theme if wanted)
      config.py      optional shift-click behaviour (Settings button)
PlaceResource/                     deployed to Documents/Gensler/Python/PlaceResource
  lib/               all Revit logic; each script's _find_lib() puts it on sys.path
  config/            legends.json, parameter_aliases.json, schema.json (must sit next to lib/)
  tests/             pure-Python unittest, no Revit (not deployed)
```

- There is no `.extension` or `.tab` folder in this repo. The panel is dropped into the user's existing tab.
- `_find_lib()` is duplicated in every script (it runs before any import is possible). Change all copies together. Lookup order: `PLACE_RESOURCE_HOME`, `PlaceResource` next to the panel, then `Documents/Gensler/Python/PlaceResource` under OneDrive or the user profile.

Rules:
- Scripts stay thin. Revit calls go into a `lib/*_service.py`.
- Office values (text styles, spacing, names, parameters) go into `config/*.json`, never into Python.
- Import `DB` through `version_adapter.get_db()` inside functions so `lib/` modules import without Revit and stay unit-testable.
- Raise `errors.LegendToolError` subclasses with an actionable message. Scripts catch them and call `reporting.alert_error`.
- Tool-created elements must be marked with `identity.write_element_identity`. Delete only through `identity.delete_managed_elements`.
- Never modify model instances or type parameters. Only the generated legend, its managed annotation and viewport position.

## Engine selection (check first)

- pyRevit runs IronPython 2.7 unless the script's **first line** is `#! python3`. A coding comment does not select CPython.
- This extension needs CPython 3 (`datetime.timezone`, `open(..., encoding=)`). Every `script.py` must start with:
  ```python
  #! python3
  # -*- coding: utf-8 -*-
  ```
- If IronPython support is ever wanted: no f-strings, use `io.open`, no `timezone`, no keyword-only args.

## CPython / pythonnet pitfalls

- **.NET interfaces** (`IFailuresPreprocessor`, `ISelectionFilter`, `IExternalEventHandler`): the class needs `__namespace__` and must be defined **once per Revit session**. The CPython engine is shared, so a second definition throws "duplicate type name". Cache the class on a module-level global or on `sys`.
- **Generics**: `List[DB.ElementId]()`, `entity.Get[String](field)`, `entity.Set[String](field, value)`.
- **out/ref parameters** come back as a tuple: `ok, value = obj.TryGet(...)`.
- **`pyrevit.forms` does not work under CPython.** pyRevit replaces the whole module with stubs that raise `PyRevitCPythonNotSupported` (`alert`, `SelectFromList`, `CommandSwitchWindow`, `FlexForm`, `pick_file`, `ask_for_*`, `ProgressBar`, WPF windows). Use `lib/dialogs.py`: `alert`, `ask_yes_no`, `choose_command` (TaskDialog, max 4 options), `choose_from_list` (WinForms, filterable), `pick_file`. `pyrevit.script` (output window, logger, `linkify`) still works.
- Enum to text: `value.ToString()`, not `str(value)`.

## Revit API pitfalls

| Wrong | Right |
| --- | --- |
| `view.IsHidden(element)` | `element.IsHidden(view)` |
| `except DB.OperationCanceledException` | `from Autodesk.Revit.Exceptions import OperationCanceledException` |
| `element_id.IntegerValue` | `version_adapter.element_id_value(id)` (`.Value` in 2024+, `IntegerValue` removed in 2026) |
| `DB.ElementId(int)` | `version_adapter.make_element_id(value)` |
| `DisplayUnitType` | `UnitTypeId` / `ForgeTypeId` (2021+); internal units are decimal feet. Use `units.mm_to_internal` |
| `FilteredElementCollector(doc).OfClass(TextNote)` to find legend notes | `FilteredElementCollector(doc, legend_view.Id)`, which is view-scoped, fast and already owner-filtered |

Legends:
- No public API creates a legend view or a `LegendComponent`. Duplicate a template legend (`ViewDuplicateOption.WithDetailing`), copy a seed with `ElementTransformUtils.CopyElement`, retarget via `BuiltInParameter.LEGEND_COMPONENT`, and read the value back.
- `LEGEND_COMPONENT_VIEW` has no documented integer map. Never write a guessed integer.
- `get_BoundingBox(view)` is `None` until `doc.Regenerate()`. Measure after regenerating.

Visibility:
- `FilteredElementCollector(doc, view.Id)` applies phase, filters, hide, crop, worksets and design options. It is not a pixel-perfect render. Linked elements are not filtered by host view settings.

Performance:
- Filter with quick filters (`OfCategory`, `OfClass`, `WhereElementIsNotElementType`) before Python loops.
- Never scan the whole document inside a per-legend or per-type loop. Collect once and pass the result down.

## Transactions and UI

- Order: read, then plan, then show the dialog, then **only then** open the `TransactionGroupContext` with `TransactionContext` steps (`lib/transactions.py`). Never open a modal dialog inside a transaction.
- Any exception must roll back the whole group. Do not catch-and-continue inside a transaction unless it is a `SubTransaction` for an optional feature.
- Do not change `uidoc.ActiveView` while a transaction is open.
- Copy Revit warnings into the report. Do not suppress them.
- Rocket mode keeps modules loaded. Read settings on every click and don't cache document objects in module globals.

## Output

- Use `reporting.py` (`print_plan`, `print_report`) and `output.linkify(element_id)` for element links.
- Messages are plain statements of what happened and what the user should do next.

## Tests

From `PlaceResource`:
```bash
python -m unittest discover -s tests -v
```
- Add tests for pure logic (layout, sorting, parameter fallback, config validation). Keep Revit calls out of the tested functions.
- For Revit behaviour, add a line to the README manual checklist instead of claiming it works.

## Review checklist

- [ ] `#! python3` is the first line of every changed `script.py`
- [ ] No `DB` import at module top level in `lib/`
- [ ] No `pyrevit.forms` import; dialogs go through `lib/dialogs.py`
- [ ] No dialog inside a transaction; failure rolls back the group
- [ ] Created elements are marked; deletes go through `delete_managed_elements`
- [ ] No whole-document collector inside a loop
- [ ] ElementIds go through `version_adapter`
- [ ] New settings are in JSON, `schema.json` and `configuration.py` validation
- [ ] `python -m unittest discover -s tests` passes
- [ ] README is updated and no untested version is claimed
