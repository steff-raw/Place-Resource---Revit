# -*- coding: utf-8 -*-
"""Build the category's legend symbol family inside Revit.

Result: a Generic Annotation family, e.g. "PR Legend - Walls.rfa", with
- one type per code (type name = Type Mark, e.g. IWS-105),
- type parameters Code and Description filled per type,
- one hatch swatch (filled region) per hatch used, each shown only in the
  types that use it (a Yes/No "Show <hatch>" type parameter per swatch).

Text: the Revit API cannot create labels. The builder therefore starts from a
seed family made once by hand (Code and Description labels, see README). Without
a seed it starts from the Generic Annotation template and the family shows
the swatch only.

The family is saved under PlaceResource/config/families and loaded into the model.
Nothing is sent anywhere and no other program is started.
"""

import os
import re

from errors import LegendOperationError
from legend_library import apply_pattern, normalize_code
from logging_service import get_logger
from units import mm_to_internal

LOGGER = get_logger("family_builder")

CODE_PARAMETER = "Code"
_INVALID_PARAMETER_CHARS = re.compile(r"[\\:{}\[\]|;<>?`~\"]")
_TEMPLATE_NAMES = ("Metric Generic Annotation.rft", "Generic Annotation.rft")


def plan_family(rows, available_hatches, hatch_name_pattern, category):
    """Decide swatches, parameters and types. Pure: no Revit calls.

    ``rows``: [{"code", "description", "hatch" (optional explicit hatch name)}] in the order wanted.
    ``available_hatches``: names of Filled Region Types in the project.
    Returns {"types": [{"name", "code", "description", "hatch", "show": {param: 0|1}}],
             "hatches": [{"name", "parameter"}], "missing_hatch": [codes], "duplicates": [codes]}.
    """
    available = {}
    for name in available_hatches:
        available.setdefault(name.strip().lower(), name)
    hatches = []
    hatch_params = {}
    types = []
    missing = []
    duplicates = []
    seen = set()
    for row in rows:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        key = normalize_code(code)
        if key in seen:
            duplicates.append(code)
            continue
        seen.add(key)
        wanted = row.get("hatch") or apply_pattern(hatch_name_pattern, category, code=code)
        hatch = available.get((wanted or "").strip().lower())
        if hatch is None:
            missing.append(code)
        elif hatch not in hatch_params:
            hatch_params[hatch] = parameter_name("Show " + hatch)
            hatches.append({"name": hatch, "parameter": hatch_params[hatch]})
        types.append({
            "name": code,
            "code": code,
            "description": row.get("description") or "",
            "hatch": hatch,
            "show": {item["parameter"]: (1 if item["name"] == hatch else 0) for item in hatches},
        })
    # Types made before a later hatch was added still need an explicit 0 for it.
    for family_type in types:
        for item in hatches:
            family_type["show"].setdefault(item["parameter"], 0)
    return {"types": types, "hatches": hatches, "missing_hatch": missing, "duplicates": duplicates}


def parameter_name(text):
    """A family parameter name Revit accepts."""
    cleaned = _INVALID_PARAMETER_CHARS.sub("-", text or "").strip()
    return cleaned[:120] or "Show"


def family_folder(config):
    """Absolute folder where built families are saved (PlaceResource/config/families by default)."""
    folder = config["builder"]["family_folder"] or "families"
    if os.path.isabs(folder):
        return folder
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "config", folder)


def seed_path(config):
    """Absolute path of the seed family, or None when not configured or not found."""
    configured = (config["builder"].get("seed_family_path") or "").strip()
    if not configured:
        return None
    path = configured if os.path.isabs(configured) else os.path.join(family_folder(config), configured)
    return path if os.path.isfile(path) else None


def find_template(application):
    """Find the Generic Annotation family template on this machine."""
    roots = []
    try:
        if application.FamilyTemplatePath:
            roots.append(application.FamilyTemplatePath)
    except Exception:
        pass
    for root in roots:
        for folder, _dirs, files in os.walk(root):
            for name in _TEMPLATE_NAMES:
                if name in files:
                    return os.path.join(folder, name)
    return None


def model_rows(doc, config):
    """Rows from model types of the category: code = Type Mark, description from the model type."""
    from collectors import type_mark
    from version_adapter import get_db
    DB = get_db()
    built_in = getattr(DB.BuiltInCategory, config["revit_category"], None)
    if built_in is None:
        raise LegendOperationError("Revit has no built-in category named {0}.".format(config["revit_category"]))
    rows = {}
    for element_type in DB.FilteredElementCollector(doc).OfCategory(built_in).WhereElementIsElementType():
        mark = type_mark(element_type)
        if not mark or normalize_code(mark) in rows:
            continue
        rows[normalize_code(mark)] = {
            "code": mark,
            "description": _text_parameter(element_type, config["description_parameter"])
                           or _text_parameter(element_type, "Type Comments"),
            "source": _name(element_type),
        }
    from layout_engine import natural_sort_key
    return sorted(rows.values(), key=lambda row: natural_sort_key(row["code"]))


def region_type_rows(doc):
    """Rows from the project's Filled Region Types: code = hatch name (for zone categories)."""
    from layout_engine import natural_sort_key
    names = sorted(filled_region_types(doc).keys(), key=natural_sort_key)
    return [{"code": name, "description": "", "hatch": name, "source": "Filled Region Type"} for name in names]


def filled_region_types(doc):
    """Map of Filled Region Type name to element."""
    from version_adapter import get_db
    DB = get_db()
    result = {}
    for region_type in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
        name = _name(region_type)
        if name:
            result[name] = region_type
    return result


def build_family(doc, config, rows):
    """Create, save and load the family. Returns a report dictionary.

    Runs with no transaction open in the project. Family document edits happen in their own transaction.
    """
    from transactions import TransactionContext
    from version_adapter import get_db
    DB = get_db()
    category = config["name"]
    report = {"status": "failed", "family_name": config["family_name"], "path": None,
              "types": 0, "warnings": [], "errors": [], "notices": []}
    project_hatches = filled_region_types(doc)
    plan = plan_family(rows, project_hatches.keys(), config["builder"]["hatch_name_pattern"], category)
    if plan["duplicates"]:
        report["warnings"].append("Codes listed twice were used once: {0}.".format(", ".join(plan["duplicates"])))
    if plan["missing_hatch"]:
        report["warnings"].append(
            "No Filled Region Type named like the code for: {0}. Those types show no hatch. Create Filled Region "
            "Types named as the code (pattern '{1}') and build again.".format(
                ", ".join(plan["missing_hatch"]), config["builder"]["hatch_name_pattern"]
            )
        )
    if not plan["types"]:
        report["errors"].append("No codes were chosen, so no family was built.")
        return report

    application = doc.Application
    seed = seed_path(config)
    if seed:
        try:
            family_doc = application.OpenDocumentFile(seed)
        except Exception as ex:
            report["errors"].append(
                "The seed family {0} could not be opened. Close it if it is open in Revit. {1}".format(seed, ex)
            )
            return report
        report["notices"].append("Started from seed family {0}.".format(seed))
    else:
        template = find_template(application)
        if template is None:
            report["errors"].append(
                "No seed family and no Generic Annotation template (.rft) was found under {0}. Set "
                "builder.seed_family_path in library_legends.json.".format(getattr(application, "FamilyTemplatePath", "?"))
            )
            return report
        try:
            family_doc = application.NewFamilyDocument(template)
        except Exception as ex:
            report["errors"].append("A family could not be started from {0}. {1}".format(template, ex))
            return report
        report["warnings"].append(
            "No seed family was found, so the family has hatch swatches but no text. Make the seed once "
            "(README: 'Seed family') and build again to show Code and Description."
        )

    try:
        with TransactionContext(family_doc, "Build legend family"):
            _fill_family(DB, doc, family_doc, config, plan, project_hatches, report)
        folder = family_folder(config)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        path = os.path.join(folder, "{0}.rfa".format(config["family_name"]))
        options = DB.SaveAsOptions()
        options.OverwriteExistingFile = True
        family_doc.SaveAs(path, options)
        report["path"] = path
        _load_into_project(DB, doc, family_doc, path, config, report)
    except LegendOperationError as ex:
        report["errors"].append(str(ex))
        return report
    except Exception as ex:
        LOGGER.exception("Family build failed")
        report["errors"].append("The family could not be built. {0}".format(ex))
        return report
    finally:
        try:
            family_doc.Close(False)
        except Exception:
            pass
    report["types"] = len(plan["types"])
    if report["status"] == "failed" and not report["errors"]:
        report["status"] = "built"
    return report


def _fill_family(DB, project_doc, family_doc, config, plan, project_hatches, report):
    manager = family_doc.FamilyManager
    code_param = _ensure_text_parameter(DB, manager, CODE_PARAMETER)
    description_param = _ensure_text_parameter(DB, manager, config["description_parameter"])

    family_hatches = _copy_hatches(DB, project_doc, family_doc, [item["name"] for item in plan["hatches"]], project_hatches)
    view = _family_view(DB, family_doc)
    width = mm_to_internal(config["builder"]["swatch_width_mm"])
    height = mm_to_internal(config["builder"]["swatch_height_mm"])
    show_params = {}
    for item in plan["hatches"]:
        region_type = family_hatches.get(item["name"])
        if region_type is None:
            report["warnings"].append("Hatch '{0}' could not be copied into the family.".format(item["name"]))
            continue
        region = _swatch(DB, family_doc, view, region_type.Id, width, height)
        parameter = _ensure_yes_no_parameter(DB, manager, item["parameter"])
        visible = region.get_Parameter(DB.BuiltInParameter.IS_VISIBLE_PARAM)
        manager.AssociateElementParameterToFamilyParameter(visible, parameter)
        show_params[item["parameter"]] = parameter

    existing = {}
    for family_type in manager.Types:
        existing[normalize_code(family_type.Name)] = family_type
    for spec in plan["types"]:
        family_type = existing.get(normalize_code(spec["name"]))
        if family_type is None:
            family_type = manager.NewType(spec["name"])
        manager.CurrentType = family_type
        manager.Set(code_param, spec["code"])
        manager.Set(description_param, spec["description"])
        for name, parameter in show_params.items():
            manager.Set(parameter, int(spec["show"].get(name, 0)))

    # Remove types that are not codes (for example the seed's default type), so they never
    # show up as legend rows. Revit keeps at least one type, and plan types always exist here.
    wanted = set(normalize_code(spec["name"]) for spec in plan["types"])
    for family_type in list(manager.Types):
        if normalize_code(family_type.Name) in wanted:
            continue
        manager.CurrentType = family_type
        manager.DeleteCurrentType()
        report["notices"].append("Removed family type '{0}' (not a code).".format(family_type.Name))


def _ensure_text_parameter(DB, manager, name):
    parameter = manager.get_Parameter(name)
    if parameter is not None:
        return parameter
    return manager.AddParameter(name, DB.GroupTypeId.Text, DB.SpecTypeId.String.Text, False)


def _ensure_yes_no_parameter(DB, manager, name):
    parameter = manager.get_Parameter(name)
    if parameter is not None:
        return parameter
    return manager.AddParameter(name, DB.GroupTypeId.Graphics, DB.SpecTypeId.Boolean.YesNo, False)


def _copy_hatches(DB, project_doc, family_doc, names, project_hatches):
    """Copy the named Filled Region Types into the family. Returns name -> type in the family."""
    from System.Collections.Generic import List
    in_family = filled_region_types(family_doc)
    wanted = [name for name in names if name not in in_family and name in project_hatches]
    if wanted:
        ids = List[DB.ElementId]()
        for name in wanted:
            ids.Add(project_hatches[name].Id)
        DB.ElementTransformUtils.CopyElements(project_doc, ids, family_doc, DB.Transform.Identity, DB.CopyPasteOptions())
        in_family = filled_region_types(family_doc)
    return {name: in_family[name] for name in names if name in in_family}


def _family_view(DB, family_doc):
    for view in DB.FilteredElementCollector(family_doc).OfClass(DB.View):
        try:
            if not view.IsTemplate and view.ViewType != DB.ViewType.ProjectBrowser:
                return view
        except Exception:
            continue
    raise LegendOperationError("The family has no view to draw the swatch in.")


def _swatch(DB, family_doc, view, type_id, width, height):
    """Rectangle from the origin to the right and down, so labels can sit to its right."""
    from System.Collections.Generic import List
    corners = [DB.XYZ(0, 0, 0), DB.XYZ(width, 0, 0), DB.XYZ(width, -height, 0), DB.XYZ(0, -height, 0)]
    loop = DB.CurveLoop()
    for start, end in zip(corners, corners[1:] + corners[:1]):
        loop.Append(DB.Line.CreateBound(start, end))
    loops = List[DB.CurveLoop]()
    loops.Add(loop)
    return DB.FilledRegion.Create(family_doc, type_id, view.Id, loops)


def _load_into_project(DB, doc, family_doc, path, config, report):
    """Load the saved family. When it is already loaded, try to replace it; otherwise say how."""
    from symbol_library import find_family
    if find_family(doc, config["family_name"]) is None:
        from transactions import TransactionContext
        with TransactionContext(doc, "Load legend family"):
            loaded = doc.LoadFamily(path)
        if loaded is False:
            raise LegendOperationError("Revit did not load {0}.".format(path))
        report["status"] = "loaded"
        report["notices"].append("Family '{0}' was loaded into the model.".format(config["family_name"]))
        return
    try:
        family_doc.LoadFamily(doc)
        report["status"] = "reloaded"
        report["notices"].append("Family '{0}' was reloaded; legends using it update automatically.".format(
            config["family_name"]
        ))
    except Exception as ex:
        report["status"] = "saved"
        report["warnings"].append(
            "The family was saved but not reloaded ({0}). Load it with Insert > Load Family > {1} and choose "
            "'Overwrite the existing version and its parameter values'.".format(ex, path)
        )


def _text_parameter(element, name):
    try:
        parameter = element.LookupParameter(name)
        if parameter is None:
            return ""
        return (parameter.AsString() or parameter.AsValueString() or "").strip()
    except Exception:
        return ""


def _name(element):
    try:
        return element.Name or ""
    except Exception:
        return ""
