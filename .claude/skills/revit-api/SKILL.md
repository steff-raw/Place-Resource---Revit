---
name: revit-api
description: Revit API reference (2025 baseline) for writing and checking Revit API calls from pyRevit. Use whenever code calls Autodesk.Revit.DB / UI members - collectors, filters, transactions, failures, views, sheets, viewports, legends, text notes, detail curves, parameters, Extensible Storage, walls, compound structures, units, ElementId, geometry - or when checking whether a class, method, overload or return type exists, or what changed between Revit versions.
---

# Revit API skill

Baseline: **Revit 2025 API** (.NET 8, 64-bit `ElementId`).

This reference was written from knowledge, not copied from the docs site. Items marked **(verify)** must be checked on revitapidocs.com before relying on them. If a call is not in the reference files, look it up. Don't guess a signature.

## Files

| File | Covers |
| --- | --- |
| `references/api-reference.md` | Classes and members by area, with return types and pyRevit (pythonnet) usage |
| `references/version-changes.md` | What was renamed or removed per version (2021–2026) |

Read only the section you need.

## Looking up a member that isn't listed

1. The site is `https://www.revitapidocs.com/<year>/`, where `<year>` is 2015–2026. Pages are `<guid>.htm` and the GUIDs are not guessable, so use the site search or a web search: `site:revitapidocs.com 2025 <Class> <Member>`.
2. Confirm on the page:
   - namespace
   - static or instance
   - every overload
   - **return type** (for example, a collection vs. a single `ElementId`)
   - exceptions thrown
   - "Remarks" limits (view type, transaction required)
3. Check the same page for the **oldest supported year** too. A member can be missing in older versions.
4. If the host blocks the site, say so and mark the call **(verify)** in the code comment or review. Don't present it as confirmed.

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
- Temporary hide/isolate: `View.IsElementVisibleInTemporaryViewMode(TemporaryViewMode, ElementId)`.
