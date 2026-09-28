# Changelog

## Unreleased

- Select the CPython 3 engine with `#! python3` on every button script. Without it pyRevit ran the scripts in IronPython and imports failed.
- Catch `Autodesk.Revit.Exceptions.OperationCanceledException` when the sheet point pick is cancelled. The previous `DB.OperationCanceledException` does not exist and turned a cancel into a failure.
- Use `Element.IsHidden(view)` for the hidden-element and hidden-link checks. The reversed call always threw and the check was skipped.
- Define the Revit warning collector class once per session. A second definition failed in the shared CPython engine and warnings were lost from the report.
- Find managed legend elements with an owner-view filter instead of scanning every text note, detail line, dimension, and reference plane in the model.
- Always rebuild managed borders and layer graphics. They no longer stack up when entry removal is off or `layer_reference_planes` is on.
- Remove the duplicated seed from a new legend when the view has no visible types, instead of leaving an orphan component.
- Show type names instead of ids in the removal prompt of Place Legend on Sheet.
- Read the first id from `ElementTransformUtils.CopyElement`, which returns a collection. Legends with more than one type failed on the second component.
- Create border and layer lines with `doc.Create.NewDetailCurve`. `DetailCurve.Create` does not exist, so `show_border` and `fallback_detail_lines` failed.
- Create layer reference planes with `doc.Create.NewReferencePlane`.
- Wall-only include flags are required only for `OST_Walls`. Other categories use `in_place`, `linked_models`, and `demolished`, and a wall-only flag on them is rejected. The door definition was updated to match.

## 1.0.0

- Add the Place Resource tab and the view-based legend commands.
- Generate wall legends from types visible in the active view, using a duplicated template legend and a seed legend component.
- Store legend identity and managed-element identity in Extensible Storage.
- Keep office names, styles, spacing, and parameter lookup in JSON.
- Add unit tests for settings, natural sort, layout, and parameter fallback.

No Revit or pyRevit version has been recorded as tested.
