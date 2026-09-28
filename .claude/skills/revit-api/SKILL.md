---
name: revit-api
description: Revit API reference (2025 baseline) for writing and checking Revit API calls from pyRevit. Use whenever code calls Autodesk.Revit.DB / UI members - collectors, filters, transactions, failures, views, sheets, viewports, legends, text notes, detail curves, parameters, Extensible Storage, walls, compound structures, units, ElementId, geometry - or when checking whether a class, method, overload or return type exists, or what changed between Revit versions.
---

# Revit API skill

Baseline: **Revit 2025 API** (.NET 8, 64-bit `ElementId`).

This reference was written from knowledge, not copied from the docs. Items marked **(verify)** must be checked in the local Revit SDK help before relying on them. If a call is not in the reference files, don't guess a signature.

The `offline-security` skill applies: no web lookups for this project.

## Files

| File | Covers |
| --- | --- |
| `references/api-reference.md` | Classes and members by area, with return types and pyRevit (pythonnet) usage |
| `references/version-changes.md` | What was renamed or removed per version (2021–2026) |

Read only the section you need.

## Looking up a member that isn't listed (offline only)

1. Don't search the web or fetch documentation sites. The `offline-security` skill forbids it.
2. Ask the user to check the **local Revit SDK help**, `RevitAPI.chm`. It installs with the Revit SDK for their Revit year and opens offline.
3. What to confirm there:
   - namespace
   - static or instance
   - every overload
   - **return type** (for example, a collection vs. a single `ElementId`)
   - exceptions thrown
   - "Remarks" limits (view type, transaction required)
4. Check the **oldest supported Revit year** too. A member can be missing in older versions.
5. Until it is confirmed, mark the call **(verify)** in the code comment or review, and write it so a missing member fails with a clear message.
6. Once the user confirms a member, add it to `references/api-reference.md` so the next lookup stays local.

## Rules for using the API from pyRevit

- `from pyrevit import DB, UI, revit`. In this repo, get `DB` through `version_adapter.get_db()`.
- Exceptions are **not** in `DB`: `from Autodesk.Revit.Exceptions import OperationCanceledException, InvalidOperationException, ArgumentException`.
- `ICollection<ElementId>` arguments: `List[DB.ElementId](ids)` from `System.Collections.Generic`.
- Returned .NET collections iterate directly: `list(result)`. Check the return type: several `Create`/`Copy` methods return a **collection**, not one id.
- Generic methods take the type in brackets: `entity.Get[String](field)`.
- Every model change needs an open `Transaction`. Reads don't.
- Internal units are **decimal feet** and **radians**. Convert with `UnitUtils` and `UnitTypeId`.
- `get_BoundingBox(view)` and positions are stale until `doc.Regenerate()`.
- Prefer quick filters (`OfClass`, `OfCategory`, `ElementOwnerViewFilter`) before slow ones (`ElementParameterFilter`) and before Python loops.

## Known traps in this repo's area

- `ElementTransformUtils.CopyElement` returns `ICollection<ElementId>`, not one `ElementId`.
- There is no `DetailCurve.Create`. Use `doc.Create.NewDetailCurve(view, curve)`.
- `Element.IsHidden(view)`, not `view.IsHidden(element)`.
- There is no public API to create a legend view or a legend component. Duplicate a legend and copy a component.
- `DataStorage`, `Schema`, `SchemaBuilder`, `Entity` are in `DB.ExtensibleStorage`, not `DB`.
- Temporary hide/isolate: `View.IsElementVisibleInTemporaryViewMode(TemporaryViewMode, ElementId)`.
