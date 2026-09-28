# Revit API changes by version

Written from knowledge. Items marked **(verify)** must be checked in the "What's New" page of the Revit SDK or on revitapidocs.com for that year.

| Version | Change | What to do |
| --- | --- | --- |
| 2021 | `ForgeTypeId` units introduced (`UnitTypeId`, `SpecTypeId`) | Use `ForgeTypeId` everywhere new |
| 2022 | `DisplayUnitType`, `UnitType` removed. `ParameterType` deprecated. `BuiltInParameterGroup` deprecated | Use `UnitTypeId`, `SpecTypeId`, `Definition.GetDataType()`, `GroupTypeId` |
| 2023 | `ParameterType` removed **(verify)** | Use `ForgeTypeId` |
| 2024 | `ElementId` became 64-bit: `ElementId(Int64)` and `.Value`. `IntegerValue` and the `ElementId(int)` constructor deprecated. `BuiltInParameterGroup` removed **(verify)** | Read `.Value`, fall back to `.IntegerValue`. Repo: `version_adapter` |
| 2025 | Runs on **.NET 8** instead of .NET Framework 4.8. Add-ins must target `net8.0-windows`. pyRevit needs a 2025-compatible release (4.8.16+/5.x) **(verify the exact pyRevit version)** | Test pyRevit on 2025 separately. CPython engine behaviour can differ |
| 2026 | `ElementId.IntegerValue` and the `Int32` constructor **removed** **(verify)** | Code must not depend on `IntegerValue` |

## Version check from pyRevit

```python
from pyrevit import HOST_APP
year = int(HOST_APP.version)          # e.g. 2025
```

Or: `doc.Application.VersionNumber` (string).

## Rule

When a member differs by version, branch in `lib/version_adapter.py` only. Don't spread version checks through services.
