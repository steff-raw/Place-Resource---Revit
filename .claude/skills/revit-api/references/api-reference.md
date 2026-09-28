# Revit API reference (2025 baseline)

Written from knowledge. Anything marked **(verify)** must be checked on revitapidocs.com. Namespace is `Autodesk.Revit.DB` unless stated otherwise.

## Contents
1. Application and document
2. ElementId
3. Element
4. Parameters
5. Collectors and filters
6. Transactions and failures
7. Views
8. Sheets and viewports
9. Legends
10. Annotation: text, detail curves, dimensions, reference planes
11. Copy, move, delete
12. Extensible Storage
13. Walls, types, compound structure
14. Families, phases, parts, links
15. Categories and graphics styles
16. Geometry
17. Units
18. UI and selection
19. Exceptions

---

## 1. Application and document

| Member | Notes |
| --- | --- |
| `UIApplication.ActiveUIDocument` | `UIDocument`, or null |
| `UIDocument.Document` | `Document` |
| `UIDocument.ActiveView` (get/set) | Setting it switches the view. Not allowed while a transaction is open or inside some events |
| `UIDocument.RequestViewChange(View)` | Asynchronous, safe from modeless contexts |
| `UIDocument.Selection` | See §18 |
| `Document.ActiveView` | Read-only |
| `Document.GetElement(ElementId)` / `GetElement(string uniqueId)` / `GetElement(Reference)` | Returns null when missing |
| `Document.Delete(ElementId)` / `Delete(ICollection<ElementId>)` | Returns `ICollection<ElementId>` of all deleted ids, dependents included |
| `Document.Regenerate()` | Needs an open transaction |
| `Document.Create` | `Autodesk.Revit.Creation.Document`, the item factory (`NewDetailCurve`, `NewDimension`, `NewReferencePlane`, ...) |
| `Document.IsFamilyDocument`, `IsReadOnly`, `IsWorkshared`, `IsModified` | bool |
| `Document.PathName`, `Title` | string. `PathName` is empty when unsaved |
| `Document.Application` | `Autodesk.Revit.ApplicationServices.Application` (`VersionNumber`, `VersionName`) |

## 2. ElementId

| Member | Notes |
| --- | --- |
| `ElementId(Int64)` | 2024+. The `Int32` constructor is deprecated |
| `ElementId(BuiltInCategory)`, `ElementId(BuiltInParameter)` | Category/parameter ids are negative |
| `ElementId.Value` | `Int64`, 2024+ |
| `ElementId.IntegerValue` | Deprecated 2024, **removed 2026** |
| `ElementId.InvalidElementId` | Value -1 |
| `ElementId.Equals`, `==` | Compare values in Python: `a.Value == b.Value`. Repo helper: `version_adapter.element_id_value` |

## 3. Element

| Member | Returns / notes |
| --- | --- |
| `Id`, `UniqueId` | `ElementId`, string |
| `Name` | Get/set. The setter throws on views/types if the name is not unique |
| `Category` | `Category` or null |
| `Document` | Owning document (a link document for linked elements) |
| `OwnerViewId` | `InvalidElementId` for model elements, the view id for view-specific ones |
| `ViewSpecific` | bool |
| `GetTypeId()` | `ElementId` |
| `get_Parameter(BuiltInParameter)` / `get_Parameter(Guid)` / `get_Parameter(Definition)` | `Parameter` or null |
| `LookupParameter(string)` | First match by name, or null. Names are not unique |
| `GetParameters(string)` | All parameters with that name |
| `Parameters` | `ParameterSet` |
| `get_BoundingBox(View)` | `BoundingBoxXYZ` or null. Pass null for the model box |
| `IsHidden(View)` | True if permanently hidden in that view (element or category hide) |
| `CanBeHidden(View)` | bool |
| `CreatedPhaseId`, `DemolishedPhaseId` | `ElementId`. Demolished is `InvalidElementId` when not demolished |
| `DesignOption` | `DesignOption` or null |
| `WorksetId` | `WorksetId` |
| `GetEntity(Schema)`, `SetEntity(Entity)`, `DeleteEntity(Schema)`, `GetEntitySchemaGuids()` | Extensible Storage (§12) |
| `Pinned` | Get/set |
| `IsValidObject` | False after deletion or undo |

`ElementType` adds `FamilyName` (string), `CanBeRenamed`, `Duplicate(string)` → `ElementType`.

## 4. Parameters

| Member | Notes |
| --- | --- |
| `StorageType` | `String`, `Double`, `Integer`, `ElementId`, `None` |
| `AsString()`, `AsDouble()`, `AsInteger()`, `AsElementId()` | Raw values. `AsDouble` is in internal units |
| `AsValueString()` | Formatted with project units, or null |
| `HasValue` | bool |
| `Set(string / double / int / ElementId)` | Returns bool. Needs a transaction. Throws if read-only or the wrong type |
| `SetValueString(string)` | Parses using units |
| `IsReadOnly`, `IsShared`, `GUID` | `GUID` only when shared |
| `Definition.Name` | Display name, which is localized for built-ins |
| `Definition.GetDataType()` | `ForgeTypeId` (2022+). Replaces `ParameterType` |
| `Definition.GetGroupTypeId()` | `ForgeTypeId` (2022+). Replaces `BuiltInParameterGroup` |
| `GetUnitTypeId()` | `ForgeTypeId` of the display unit |
| `Id` | `ElementId`. Negative for built-ins |

Common `BuiltInParameter` values:
- `ALL_MODEL_TYPE_MARK`, `ALL_MODEL_TYPE_NAME`, `ALL_MODEL_FAMILY_NAME`, `ALL_MODEL_DESCRIPTION`, `ALL_MODEL_MARK`, `ALL_MODEL_TYPE_COMMENTS`, `ALL_MODEL_INSTANCE_COMMENTS`, `ALL_MODEL_URL`, `ALL_MODEL_MANUFACTURER`, `ALL_MODEL_MODEL`
- `SYMBOL_NAME_PARAM`, `ELEM_FAMILY_PARAM`, `ELEM_TYPE_PARAM`
- `WALL_ATTR_WIDTH_PARAM`, `FUNCTION_PARAM`, `FIRE_RATING`, `UNIFORMAT_CODE`, `KEYNOTE_PARAM`
- `DOOR_WIDTH`, `DOOR_HEIGHT`, `WINDOW_WIDTH`, `WINDOW_HEIGHT` **(verify)**
- `VIEW_PHASE`, `VIEW_PHASE_FILTER`, `VIEW_NAME`, `VIEWER_SHEET_NUMBER`, `SHEET_NUMBER`, `SHEET_NAME`
- `LEGEND_COMPONENT`, `LEGEND_COMPONENT_VIEW`, `LEGEND_COMPONENT_LENGTH` **(verify)**. See §9

## 5. Collectors and filters

`FilteredElementCollector` constructors:
- `(Document)` for the whole document
- `(Document, ElementId viewId)`: elements **visible** in that view. Applies phase, filters, hide, crop and worksets. Not valid for every view type; a schedule throws
- `(Document, ICollection<ElementId>)` to restrict to given ids
- `(Document, ElementId viewId, ElementId linkId)` **(verify, 2024+)**: link elements visible in the host view

Methods (chainable unless noted):

| Method | Notes |
| --- | --- |
| `OfClass(Type)` | Quick filter. Throws for classes without a native Revit counterpart: `Room`, `Area`, `Space`, `RoomTag`, `AreaTag`, `SpaceTag`, `Mullion`, `Panel`, `AnnotationSymbol`, `DetailCurve`/`DetailLine`/`DetailArc`, `ModelCurve`/`ModelLine`/`ModelArc`, `SymbolicCurve`. Use the parent class (`SpatialElement`, `CurveElement`, `FamilyInstance`) plus `OfCategory` **(verify full list)** |
| `OfCategory(BuiltInCategory)`, `OfCategoryId(ElementId)` | Quick filter |
| `WhereElementIsElementType()` / `WhereElementIsNotElementType()` | Quick filter |
| `WherePasses(ElementFilter)` | Any filter |
| `Excluding(ICollection<ElementId>)` | Removes ids |
| `ToElements()`, `ToElementIds()` | `IList<Element>`, `ICollection<ElementId>` (terminal) |
| `FirstElement()`, `FirstElementId()`, `GetElementCount()` | Terminal |
| `UnionWith`, `IntersectWith` | Combine collectors |

Filters:

| Filter | Kind |
| --- | --- |
| `ElementCategoryFilter(BuiltInCategory [, inverted])` | Quick |
| `ElementMulticategoryFilter(ICollection<BuiltInCategory>)` | Quick |
| `ElementClassFilter(Type)` | Quick |
| `ElementIsElementTypeFilter([inverted])` | Quick |
| `ElementOwnerViewFilter(ElementId viewId [, inverted])` | Quick. Elements owned by that view, **including hidden ones** |
| `ElementDesignOptionFilter(ElementId)` | Quick |
| `BoundingBoxIntersectsFilter(Outline)`, `BoundingBoxIsInsideFilter(Outline)` | Quick |
| `VisibleInViewFilter(Document, ElementId viewId)` | Quick. Same idea as the view collector |
| `ElementParameterFilter(FilterRule)` with `ParameterFilterRuleFactory.CreateEqualsRule(...)` | Slow |
| `ElementPhaseStatusFilter(ElementId phaseId, ElementOnPhaseStatus)` | Slow |
| `FamilyInstanceFilter(Document, ElementId symbolId)` | Slow |
| `LogicalAndFilter`, `LogicalOrFilter` | Combine filters |

## 6. Transactions and failures

| Member | Notes |
| --- | --- |
| `Transaction(Document, string)` | `Start()`, `Commit()`, `RollBack()` return `TransactionStatus`. `HasStarted()`, `HasEnded()`, `GetStatus()` |
| `Transaction.GetFailureHandlingOptions()` / `SetFailureHandlingOptions(FailureHandlingOptions)` | Set before `Commit` |
| `FailureHandlingOptions.SetFailuresPreprocessor(IFailuresPreprocessor)` | Also `SetClearAfterRollback(bool)`, `SetForcedModalHandling(bool)`, `SetDelayedMiniWarnings(bool)` |
| `TransactionGroup(Document, string)` | `Start()`, `Assimilate()` (merges into one undo), `Commit()`, `RollBack()` |
| `SubTransaction(Document)` | Only inside an open `Transaction`. `Start`, `Commit`, `RollBack` |
| `IFailuresPreprocessor.PreprocessFailures(FailuresAccessor)` | Returns `FailureProcessingResult.Continue` / `ProceedWithCommit` / `ProceedWithRollBack` |
| `FailuresAccessor.GetFailureMessages()` | `IList<FailureMessageAccessor>` |
| `FailuresAccessor.DeleteWarning(FailureMessageAccessor)`, `DeleteAllWarnings()`, `ResolveFailure(...)` | Deleting a warning suppresses it |
| `FailureMessageAccessor.GetSeverity()`, `GetDescriptionText()`, `GetFailingElementIds()` | `FailureSeverity`: `Warning`, `Error`, `DocumentCorruption` |

pyRevit shortcut: `with revit.Transaction("name"):` and `with revit.TransactionGroup("name"):`.

## 7. Views

| Member | Notes |
| --- | --- |
| `View.ViewType` | `ViewType` enum: `FloorPlan`, `CeilingPlan`, `EngineeringPlan`, `AreaPlan`, `Section`, `Elevation`, `Detail`, `ThreeD`, `DraftingView`, `Legend`, `Schedule`, `DrawingSheet`, `Report`, `Walkthrough`, `Rendering`, `SystemBrowser`, `ProjectBrowser`, `Internal`, `Undefined`, `CostReport`, `LoadsReport`, `PresureLossReport`, `ColumnSchedule`, `PanelSchedule` |
| `IsTemplate`, `ViewTemplateId` | A template is not a real view |
| `Scale` (int), `DetailLevel` (`ViewDetailLevel.Coarse/Medium/Fine/Undefined`), `Discipline` | Get/set, unless controlled by a template |
| `Duplicate(ViewDuplicateOption)` | Returns `ElementId`. Options: `Duplicate`, `WithDetailing`, `AsDependent` |
| `CanViewBeDuplicated(ViewDuplicateOption)` | bool |
| `GetFilters()` | `ICollection<ElementId>` |
| `GetFilterVisibility(ElementId)`, `GetFilterOverrides(ElementId)` | Filter state |
| `GetCategoryHidden(ElementId)`, `SetCategoryHidden(ElementId, bool)` | Category hide |
| `IsInTemporaryViewMode(TemporaryViewMode)` | `TemporaryHideIsolate`, `RevealHiddenElements`, `TemporaryViewProperties`, ... |
| `IsElementVisibleInTemporaryViewMode(TemporaryViewMode, ElementId)` | Visibility under temporary hide/isolate |
| `HideElements(ICollection<ElementId>)`, `UnhideElements(...)` | Needs a transaction |
| `PartsVisibility` | `PartsVisibility.ShowPartsOnly`, `ShowOriginalOnly`, `ShowPartsAndOriginal` |
| `CropBox`, `CropBoxActive`, `CropBoxVisible` | Crop |
| `Outline` | `BoundingBoxUV` in sheet/paper space |
| `GenLevel` | `Level` for plans |
| `Origin`, `ViewDirection`, `UpDirection`, `RightDirection` | View orientation |

Creation: `ViewPlan.Create(doc, viewFamilyTypeId, levelId)`, `ViewSection.CreateSection(doc, typeId, BoundingBoxXYZ)`, `ViewDrafting.Create(doc, typeId)`, `View3D.CreateIsometric(doc, typeId)`, `ViewSchedule.CreateSchedule(doc, categoryId)`. **There is no legend-view create method.**

## 8. Sheets and viewports

| Member | Notes |
| --- | --- |
| `ViewSheet.Create(Document, ElementId titleBlockTypeId)` | `InvalidElementId` for no title block |
| `ViewSheet.SheetNumber`, `Name` | Get/set |
| `ViewSheet.GetAllPlacedViews()` | `ISet<ElementId>` |
| `ViewSheet.GetAllViewports()` | `ICollection<ElementId>` |
| `Viewport.Create(Document, ElementId sheetId, ElementId viewId, XYZ point)` | Returns `Viewport`. Throws if the view can't be placed |
| `Viewport.CanAddViewToSheet(Document, ElementId sheetId, ElementId viewId)` | False for a model view already on any sheet. **Legends and schedules can go on many sheets** |
| `Viewport.ViewId`, `SheetId`, `OwnerViewId` | The owner is the sheet |
| `Viewport.GetBoxCenter()`, `SetBoxCenter(XYZ)`, `GetBoxOutline()` | Position on the sheet |
| `Viewport.ChangeTypeId(ElementId)`, `Rotation` | Type and rotation |
| `ScheduleSheetInstance.Create(doc, sheetId, scheduleId, XYZ)` | Schedules use this, not `Viewport` |

## 9. Legends

- There is no public `LegendComponent` create API and no legend view create API.
- Supported approach: duplicate an existing legend view (`View.Duplicate`), then copy a component (`ElementTransformUtils.CopyElement`) and retarget it.
- Legend components are category `OST_LegendComponents`, found with `FilteredElementCollector(doc, legendView.Id).OfCategory(BuiltInCategory.OST_LegendComponents)`.
- Component type: `BuiltInParameter.LEGEND_COMPONENT` (`ElementId`, writable) **(verify per version)**.
- View direction: `LEGEND_COMPONENT_VIEW` (integer, **no documented value map**).
- Host length: `LEGEND_COMPONENT_LENGTH` **(verify: may not exist in every version)**.
- `get_BoundingBox(legendView)` works after `Regenerate()`.

## 10. Annotation

| Member | Notes |
| --- | --- |
| `TextNote.Create(Document, ElementId viewId, XYZ position, string text, ElementId typeId)` | Returns `TextNote` |
| `TextNote.Create(Document, ElementId viewId, XYZ position, double width, string text, TextNoteOptions)` | Width is paper-space feet |
| `TextNote.Text`, `Width`, `HorizontalAlignment` (`HorizontalTextAlignment`), `VerticalAlignment`, `Coord`, `TextNoteType` | Width is paper-space feet |
| `TextNote.GetFormattedText()` / `SetFormattedText(FormattedText)` | Rich text |
| `TextNoteType` | `FilteredElementCollector(doc).OfClass(TextNoteType)` |
| `doc.Create.NewDetailCurve(View, Curve)` | Returns `DetailCurve`. **There is no `DetailCurve.Create`** |
| `doc.Create.NewDetailCurveArray(View, CurveArray)` | Returns `DetailCurveArray` |
| `CurveElement.LineStyle` | Get/set with a `GraphicsStyle` element |
| `CurveElement.GetLineStyleIds()` | Valid styles |
| `doc.Create.NewDimension(View, Line, ReferenceArray [, DimensionType])` | Returns `Dimension` |
| `doc.Create.NewReferencePlane(XYZ bubbleEnd, XYZ freeEnd, XYZ cutVec, View)` | Returns `ReferencePlane`. Use this factory method (the repo does); don't assume a static `ReferencePlane.Create` **(verify)** |
| `ReferencePlane.GetReference()` | `Reference` for dimensions |
| `FilledRegion.Create(doc, typeId, viewId, IList<CurveLoop>)` | Filled region |
| `IndependentTag.Create(doc, typeId, viewId, Reference, addLeader, TagOrientation, XYZ)` | 2019+ overload |

## 11. Copy, move, delete

| Member | Returns |
| --- | --- |
| `ElementTransformUtils.CopyElement(Document, ElementId, XYZ translation)` | **`ICollection<ElementId>`**. Take the first id |
| `ElementTransformUtils.CopyElements(Document, ICollection<ElementId>, XYZ)` | `ICollection<ElementId>` |
| `ElementTransformUtils.CopyElements(View source, ICollection<ElementId>, View dest, Transform, CopyPasteOptions)` | `ICollection<ElementId>`. View-specific copy |
| `ElementTransformUtils.CopyElements(Document src, ICollection<ElementId>, Document dest, Transform, CopyPasteOptions)` | Between documents |
| `ElementTransformUtils.MoveElement(Document, ElementId, XYZ)` / `MoveElements(...)` | void |
| `ElementTransformUtils.RotateElement(Document, ElementId, Line axis, double radians)` | void |
| `ElementTransformUtils.MirrorElement(Document, ElementId, Plane)` | void |
| `Document.Delete(...)` | `ICollection<ElementId>` |

`CopyPasteOptions.SetDuplicateTypeNamesHandler(IDuplicateTypeNamesHandler)` controls duplicate type names.

## 12. Extensible Storage (`Autodesk.Revit.DB.ExtensibleStorage`)

| Member | Notes |
| --- | --- |
| `Schema.Lookup(Guid)` | `Schema` or null |
| `Schema.ListSchemas()` | All loaded schemas |
| `SchemaBuilder(Guid)` | Then `SetSchemaName` (alphanumeric, starts with a letter), `SetVendorId` (must match the add-in's registered vendor for non-public access), `SetReadAccessLevel` / `SetWriteAccessLevel(AccessLevel.Public/Vendor/Application)`, `SetDocumentation` |
| `SchemaBuilder.AddSimpleField(string, Type)`, `AddArrayField`, `AddMapField` | Double fields need `SetSpec(SpecTypeId.Length)` etc. |
| `SchemaBuilder.Finish()` | Returns `Schema` |
| `Entity(Schema)`, `Entity.IsValid()`, `Entity.Schema` | Entity |
| `Entity.Set<T>(string or Field, T [, ForgeTypeId unit])`, `Entity.Get<T>(string or Field [, ForgeTypeId])` | pythonnet: `entity.Set[String](field, value)` |
| `Element.SetEntity(Entity)`, `GetEntity(Schema)`, `DeleteEntity(Schema)` | Needs a transaction to write |
| `DataStorage.Create(Document)` | Invisible element for document-level data |

Schema GUIDs are permanent. Changing fields needs a new GUID.

## 13. Walls, types, compound structure

| Member | Notes |
| --- | --- |
| `Wall.WallType`, `Wall.Width`, `Wall.Flipped`, `Wall.Orientation` | Wall properties |
| `Wall.IsStackedWallMember`, `Wall.StackedWallOwnerId` | Stacked walls |
| `Wall.CurtainGrid` | null for non-curtain walls |
| `Wall.Create(doc, Curve, wallTypeId, levelId, height, offset, flip, structural)` | Creation |
| `WallType.Kind` | `WallKind.Basic`, `Curtain`, `Stacked`, `Unknown` |
| `WallType.Width` | Internal feet |
| `WallType.Function` | `WallFunction` |
| `HostObjAttributes.GetCompoundStructure()` | `CompoundStructure` or null (curtain/stacked). A copy: call `SetCompoundStructure` to write |
| `CompoundStructure.GetLayers()` | `IList<CompoundStructureLayer>` |
| `CompoundStructure.GetWidth()`, `GetCoreBoundaryLayerIndex(ShellLayerType)`, `GetFirstCoreLayerIndex()`, `GetLastCoreLayerIndex()` | Layer layout |
| `CompoundStructureLayer.Width`, `MaterialId`, `Function` (`MaterialFunctionAssignment`: `Structure`, `Substrate`, `Insulation`, `Finish1`, `Finish2`, `Membrane`, `StructuralDeck`) | Layer data |
| Floors, roofs, ceilings | Also `HostObjAttributes` → same compound-structure API |

## 14. Families, phases, parts, links

| Member | Notes |
| --- | --- |
| `FamilyInstance.Symbol` | `FamilySymbol` |
| `FamilyInstance.Host`, `FromRoom`, `ToRoom`, `FacingOrientation`, `HandOrientation` | Host and orientation |
| `FamilySymbol.Family`, `IsActive`, `Activate()` | Activate before placing |
| `Family.IsInPlace`, `FamilyCategory`, `GetFamilySymbolIds()` | Family data |
| `doc.Create.NewFamilyInstance(...)` | Many overloads **(verify the one you need)** |
| `Phase` | `doc.Phases` (`PhaseArray`), ordered |
| `PartUtils.HasAssociatedParts(Document, ElementId)`, `GetAssociatedParts(...)`, `IsValidForCreateParts(...)` | Parts |
| `RevitLinkInstance.GetLinkDocument()` | null when unloaded |
| `RevitLinkInstance.GetTotalTransform()` | Link transform |
| `RevitLinkType` | Link type |
| `DesignOption.GetActiveDesignOptionId(Document)` | Static |

## 15. Categories and graphics styles

| Member | Notes |
| --- | --- |
| `Category.GetCategory(Document, BuiltInCategory)` | Category |
| `Category.Id`, `Name`, `SubCategories`, `Parent`, `CategoryType` | Category data |
| `Category.GetGraphicsStyle(GraphicsStyleType.Projection / Cut)` | Line style for detail curves: `Category.GetCategory(doc, OST_Lines).SubCategories` |
| `doc.Settings.Categories` | `Categories` map |
| `BuiltInCategory` | `OST_Walls`, `OST_Doors`, `OST_Windows`, `OST_Floors`, `OST_Ceilings`, `OST_Roofs`, `OST_Stairs`, `OST_Furniture`, `OST_GenericModel`, `OST_Columns`, `OST_StructuralColumns`, `OST_Casework`, `OST_SpecialityEquipment`, `OST_LegendComponents`, `OST_TextNotes`, `OST_Lines`, `OST_Dimensions`, `OST_CLines` (reference planes), `OST_Viewports`, `OST_Sheets`, `OST_TitleBlocks`, `OST_Rooms`, `OST_Parts` |

## 16. Geometry

| Member | Notes |
| --- | --- |
| `XYZ(x, y, z)`, `XYZ.Zero`, `BasisX/Y/Z` | `Add`, `Subtract`, `Multiply`, `DistanceTo`, `Normalize`, `CrossProduct`, `DotProduct`, `IsAlmostEqualTo` |
| `Line.CreateBound(XYZ, XYZ)` | Throws below `Application.ShortCurveTolerance` |
| `Line.CreateUnbound(XYZ, XYZ direction)` | Unbound line |
| `Arc.Create(...)`, `CurveLoop`, `CurveArray`, `ReferenceArray` | Curves and arrays |
| `BoundingBoxXYZ.Min`, `Max`, `Transform`, `Enabled` | Bounding box |
| `Outline(XYZ min, XYZ max)` | For bounding-box filters |
| `Transform.Identity`, `CreateTranslation(XYZ)`, `CreateRotation(XYZ axis, double)`, `OfPoint(XYZ)` | Transforms |
| `Plane.CreateByNormalAndOrigin(XYZ, XYZ)`, `SketchPlane.Create(doc, Plane)` | Planes |
| `Element.get_Geometry(Options)` | `GeometryElement` of `Solid`, `GeometryInstance`, `Curve`, ... |

## 17. Units (2021+ `ForgeTypeId`)

| Member | Notes |
| --- | --- |
| `UnitUtils.ConvertToInternalUnits(double, ForgeTypeId)` | `UnitTypeId.Millimeters`, `Meters`, `Degrees`, ... |
| `UnitUtils.ConvertFromInternalUnits(double, ForgeTypeId)` | Reverse |
| `SpecTypeId.Length`, `Area`, `Volume`, `Angle` | Spec (data type) ids |
| `doc.GetUnits().GetFormatOptions(SpecTypeId.Length)` | Project format |
| `UnitFormatUtils.Format(Units, ForgeTypeId spec, double, bool forEditing)` | Formatting |

1 ft = 304.8 mm. `DisplayUnitType` and `UnitType` were removed in 2022.

## 18. UI and selection (`Autodesk.Revit.UI`, `.UI.Selection`)

| Member | Notes |
| --- | --- |
| `Selection.GetElementIds()`, `SetElementIds(ICollection<ElementId>)` | Current selection |
| `Selection.PickObject(ObjectType, [ISelectionFilter,] string prompt)` | Returns `Reference`. `ObjectType.Element`, `PointOnElement`, `Edge`, `Face`, `LinkedElement` |
| `Selection.PickObjects(...)` | `IList<Reference>` |
| `Selection.PickPoint([ObjectSnapTypes,] string)` | `XYZ`. The active view needs a work plane (sheets and plans are fine) |
| `Selection.PickBox(PickBoxStyle, string)` | `PickedBox` |
| `Selection.PickElementsByRectangle(...)` | `IList<Element>` |
| `ISelectionFilter.AllowElement(Element)`, `AllowReference(Reference, XYZ)` | Selection filter interface |
| `TaskDialog.Show(title, message)` | pyRevit: prefer `forms.alert` |
| Cancel | Raises `Autodesk.Revit.Exceptions.OperationCanceledException` |

## 19. Exceptions (`Autodesk.Revit.Exceptions`)

- `OperationCanceledException` (user pressed Esc)
- `InvalidOperationException`, `ArgumentException`, `ArgumentNullException`, `ArgumentOutOfRangeException`
- `ModificationForbiddenException` (write outside a transaction or in a read-only context)
- `ModificationOutsideTransactionException`
- `InvalidObjectException` (element deleted or undone)
- `ForbiddenForDynamicUpdateException`
- `RegenerationFailedException`

Catch them by importing from `Autodesk.Revit.Exceptions`. Many API calls also raise the .NET `System.ArgumentException` family.
