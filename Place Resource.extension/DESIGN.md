# Technical design

This extension has not been executed inside Revit. The behaviour below is what the code does. Version-specific API results still have to be confirmed with the manual checklist in the README.

## 1. Technical design

The ribbon is **Place Resource**, and the panel is **Legends**. Commands are thin scripts. Revit calls sit in services. Layout, settings, units, and parameter fallback are pure Python so they can be tested without Revit.

A command loads JSON once, collects visible types, shows a preview, and only then opens a transaction group. The group contains three transactions: prepare the legend view, write entries, then measure and align. Any exception rolls the group back.

Walls have their own adapter. Other supported categories share one adapter that collects type ids and refuses a seed whose category does not match. Adding a category is a JSON definition plus, when the rules differ, an adapter. It is not a new command.

## 2. Revit API constraints

- `View.Duplicate` works on an existing legend. There is no create-legend method in the public API.
- `LegendComponent` can be read and copied. There is no create method. The component type is `BuiltInParameter.LEGEND_COMPONENT`. The service writes it and reads it back.
- `LEGEND_COMPONENT_VIEW` is an integer without a documented map. The code does not invent that map.
- Host length is not a confirmed built-in parameter on every version. The code sets it only when a writable parameter is present.
- `FilteredElementCollector(doc, viewId)` is the visibility filter. It is not identical to the final graphics pipeline. The collector module records the differences.
- ElementId uses `.Value` when it exists and `.IntegerValue` otherwise. That split stays in `version_adapter.py`.
- Extensible Storage schemas use public write access because pyRevit is not a vendor-signed add-in. The schema GUIDs are fixed.

## 3. Template and seed strategy

1. The project contains a real legend view named by `template_legend_name`.
2. On first use the tool duplicates it with `ViewDuplicateOption.WithDetailing`, then `Duplicate` if that option throws.
3. The duplicate is renamed from `output_name_pattern` and tagged with Extensible Storage.
4. The seed legend component in the duplicate is retargeted to the first required type. Further types are `CopyElement` copies of that seed.
5. If the generated legend has no component left, the seed is copied from the template with `CopyElements`.
6. If the type parameter is missing, read-only, or rejected, `UnsupportedRevitOperationError` rolls the group back.
7. Detail lines are not a silent substitute. They run only when `fallback_detail_lines` is true, and only after reference planes fail, and the report says they are disconnected.

The template view is never edited.

## 4. Identity model

View entity (`8f4e2c1a-6b3d-4e7f-9a21-5c8d0e4b7f63`):

- `source_view_id`, `source_view_unique_id`
- `legend_definition_id`
- `updated_utc`
- `tool_version`
- `content_hash`
- `config_schema_version`
- `managed`, `tool`, `role`

Element entity (`3c9a7e52-1d4b-4f86-b0c5-7e2a9d6f4b18`):

- `legend_definition_id`, `source_view_id`, `type_id`
- `role`: `component`, `type_label`, `heading`, `border`, `layer_reference`, `layer_dimension`, `layer_line`
- `label_parameter`, `column_index`
- `tool_version`, `managed`, `tool`

A DataStorage element (`d1b6e4a8-0c53-4a9e-8f27-6b5c3d2e1a90`) indexes those legends. The view entity remains the source of truth. Lookup matches UniqueId first, then element id, then the local JSON fallback.

The content hash covers definition id, schema version, layout settings, and each type id with its display values. Update All skips a legend when the hash is unchanged. A single Create / Update still realigns.

## 5. Folder structure

```
Place Resource.extension/
    extension.json
    README.md
    DESIGN.md
    CHANGELOG.md
    Place Resource.tab/
        Legends.panel/
            Create Update View Legend.pushbutton/
            Place Legend on Sheet.pushbutton/
            Update All Generated Legends.pushbutton/
            Audit Generated Legends.pushbutton/
            Settings.pushbutton/
    lib/
    config/
        legends.json
        parameter_aliases.json
        schema.json
    tests/
```

`lib` is at the extension root so every button can import it. Each script also inserts that folder onto `sys.path`.

## 6. Wall collection

1. Reject a read-only document, a family document, a sheet, a legend, a view template, and a view type outside `source_view_types`.
2. Collect `OST_Walls` with `WhereElementIsNotElementType()` in the source view.
3. Drop invalid type ids and elements for which `Element.IsHidden(view)` is still true.
4. Classify each wall: basic, curtain, stacked, in-place, stacked member, demolished, parts-only, linked.
5. Apply the JSON include flags. Defaults exclude curtain, stacked, members, in-place, demolished, parts-only, and links.
6. Unique the remaining instances by host `WallType` id.
7. Resolve parameters and compound-structure layers.
8. Sort with the configured keys. Natural sort is used for text. Equal keys fall back to type id so the order is stable.
9. Warn on duplicate Type Marks without merging the types.

## 7. Update algorithm

1. Find an existing legend by source view plus definition id.
2. Diff managed component type ids with the visible type ids.
3. Ask before deleting when `confirm_before_deleting` is true. No means obsolete entries stay.
4. If nothing exists, duplicate the template and write identity.
5. Retarget or copy the seed for missing types. Refresh label text for types that remain. Delete managed elements whose type is gone, and only those elements.
6. Recreate managed headings and borders. Leave every element that has no tool entity where the user put it.
7. Regenerate, measure, lay out, move.
8. Optionally rebuild layer planes in a subtransaction per type.
9. Put viewport centres back.
10. Write the new hash.

`full_rebuild` deletes managed elements and recreates them. It still does not delete unmanaged annotation. An empty visible set does not create a legend unless `create_when_empty` is true.

## 8. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Legend or component creation is refused | Template duplicate and seed copy, isolated in `legend_component_service.py`, with a hard error instead of drafted geometry |
| View-direction integers differ by version | Never written. The seed carries the direction |
| Host length cannot be set | Seed length is kept and the report says so |
| Bounding boxes are null | Configured graphic size is used and a warning is added |
| Collector and screen disagree | Notices name phase, filters, parts, temporary hide, and links |
| Linked type ids are not valid in the host | Match on family name plus type name, otherwise skip and warn |
| User annotation is deleted | Delete path checks the element entity and throws if it is absent |
| Transaction failure leaves a partial legend | One transaction group around the whole edit |
| Rocket mode serves stale JSON | Settings are read on every click and not cached on the module |
| Layer planes become model datums | Flag defaults to false. Planes are created only when the box matches the wall width, inside a subtransaction |
| Another category is assumed to work | Only walls have kind rules. The sample door definition is present and untested. The seed category is checked before a type is assigned |
