# Changelog

## Unreleased

- Select the CPython 3 engine with `#! python3` on every button script. Without it pyRevit ran the scripts in IronPython and imports failed.
- Catch `Autodesk.Revit.Exceptions.OperationCanceledException` when the sheet point pick is cancelled. The previous `DB.OperationCanceledException` does not exist and turned a cancel into a failure.
- Use `Element.IsHidden(view)` for the hidden-element and hidden-link checks. The reversed call always threw and the check was skipped.

## 1.0.0

- Add the Place Resource tab and the view-based legend commands.
- Generate wall legends from types visible in the active view, using a duplicated template legend and a seed legend component.
- Store legend identity and managed-element identity in Extensible Storage.
- Keep office names, styles, spacing, and parameter lookup in JSON.
- Add unit tests for settings, natural sort, layout, and parameter fallback.

No Revit or pyRevit version has been recorded as tested.
