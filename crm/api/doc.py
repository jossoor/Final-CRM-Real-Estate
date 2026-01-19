import json
from typing import Optional

import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.desk.form.assign_to import set_status
from frappe.model import no_value_fields
from frappe.model.document import get_controller
from frappe.utils import make_filter_tuple
from pypika import Criterion

from crm.api.views import get_views
from crm.fcrm.doctype.crm_form_script.crm_form_script import get_form_script
from crm.utils import get_dynamic_linked_docs, get_linked_docs


@frappe.whitelist()
def update_lead_status(name: str, status: str):
    if not frappe.has_permission("CRM Lead", "write", name):
        frappe.throw(_("No permission to update lead status"), frappe.PermissionError)

    frappe.db.set_value("CRM Lead", name, "status", status)
    frappe.db.commit()
    return {"name": name, "status": status}


@frappe.whitelist(allow_guest=True)
def sort_options(doctype: str):
    fields = frappe.get_meta(doctype).fields
    fields = [field for field in fields if field.fieldtype not in no_value_fields]
    fields = [
        {
            "label": _(field.label),
            "value": field.fieldname,
            "fieldname": field.fieldname,
        }
        for field in fields
        if field.label and field.fieldname
    ]

    standard_fields = [
        {"label": "Name", "fieldname": "name"},
        {"label": "Created On", "fieldname": "creation"},
        {"label": "Last Modified", "fieldname": "modified"},
        {"label": "Modified By", "fieldname": "modified_by"},
        {"label": "Owner", "fieldname": "owner"},
    ]

    for field in standard_fields:
        field["label"] = _(field["label"])
        field["value"] = field["fieldname"]
        fields.append(field)

    return fields


@frappe.whitelist(allow_guest=True)
def get_filterable_fields(doctype: str):
    allowed_fieldtypes = [
        "Check",
        "Data",
        "Float",
        "Int",
        "Currency",
        "Dynamic Link",
        "Link",
        "Long Text",
        "Select",
        "Small Text",
        "Text Editor",
        "Text",
        "Duration",
        "Date",
        "Datetime",
    ]

    c = get_controller(doctype)
    restricted_fields = []
    if hasattr(c, "get_non_filterable_fields"):
        restricted_fields = c.get_non_filterable_fields()

    res = []

    # append DocFields
    DocField = frappe.qb.DocType("DocField")
    doc_fields = get_doctype_fields_meta(DocField, doctype, allowed_fieldtypes, restricted_fields)
    res.extend(doc_fields)

    # append Custom Fields
    CustomField = frappe.qb.DocType("Custom Field")
    custom_fields = get_doctype_fields_meta(CustomField, doctype, allowed_fieldtypes, restricted_fields)
    res.extend(custom_fields)

    # append standard fields (getting error when using frappe.model.std_fields)
    standard_fields = [
        {"fieldname": "name", "fieldtype": "Link", "label": "ID", "options": doctype},
        {"fieldname": "owner", "fieldtype": "Link", "label": "Created By", "options": "User"},
        {
            "fieldname": "modified_by",
            "fieldtype": "Link",
            "label": "Last Updated By",
            "options": "User",
        },
        {"fieldname": "_user_tags", "fieldtype": "Data", "label": "Tags"},
        {"fieldname": "_liked_by", "fieldtype": "Data", "label": "Like"},
        {"fieldname": "_comments", "fieldtype": "Text", "label": "Comments"},
        {"fieldname": "_assign", "fieldtype": "Text", "label": "Assigned To"},
        {"fieldname": "creation", "fieldtype": "Datetime", "label": "Created On"},
        {"fieldname": "modified", "fieldtype": "Datetime", "label": "Last Updated On"},
    ]
    for field in standard_fields:
        if field.get("fieldname") not in restricted_fields and field.get("fieldtype") in allowed_fieldtypes:
            field["name"] = field.get("fieldname")
            res.append(field)

    for field in res:
        field["label"] = _(field.get("label"))
        field["value"] = field.get("fieldname")

    return res


@frappe.whitelist(allow_guest=True)
def get_group_by_fields(doctype: str):
    allowed_fieldtypes = [
        "Check",
        "Data",
        "Float",
        "Int",
        "Currency",
        "Dynamic Link",
        "Link",
        "Select",
        "Duration",
        "Date",
        "Datetime",
    ]

    fields = frappe.get_meta(doctype).fields
    fields = [
        field
        for field in fields
        if field.fieldtype not in no_value_fields and field.fieldtype in allowed_fieldtypes
    ]
    fields = [
        {
            "label": _(field.label),
            "fieldname": field.fieldname,
        }
        for field in fields
        if field.label and field.fieldname
    ]

    standard_fields = [
        {"label": "Name", "fieldname": "name"},
        {"label": "Created On", "fieldname": "creation"},
        {"label": "Last Modified", "fieldname": "modified"},
        {"label": "Modified By", "fieldname": "modified_by"},
        {"label": "Owner", "fieldname": "owner"},
        {"label": "Liked By", "fieldname": "_liked_by"},
        {"label": "Assigned To", "fieldname": "_assign"},
        {"label": "Comments", "fieldname": "_comments"},
        {"label": "Created On", "fieldname": "creation"},
        {"label": "Modified On", "fieldname": "modified"},
    ]

    for field in standard_fields:
        field["label"] = _(field["label"])
        fields.append(field)

    return fields


def get_doctype_fields_meta(DocField, doctype, allowed_fieldtypes, restricted_fields):
    parent = "parent" if DocField._table_name == "tabDocField" else "dt"
    return (
        frappe.qb.from_(DocField)
        .select(
            DocField.fieldname,
            DocField.fieldtype,
            DocField.label,
            DocField.name,
            DocField.options,
        )
        .where(DocField[parent] == doctype)
        .where(DocField.hidden == False)  # noqa: E712
        .where(Criterion.any([DocField.fieldtype == i for i in allowed_fieldtypes]))
        .where(Criterion.all([DocField.fieldname != i for i in restricted_fields]))
        .run(as_dict=True)
    )


@frappe.whitelist(allow_guest=True)
def get_quick_filters(doctype: str, cached: bool = True):
    meta = frappe.get_meta(doctype, cached)
    quick_filters = []

    if global_settings := frappe.db.exists("CRM Global Settings", {"dt": doctype, "type": "Quick Filters"}):
        _quick_filters = frappe.db.get_value("CRM Global Settings", global_settings, "json")
        _quick_filters = json.loads(_quick_filters) or []

        fields = []

        for filter in _quick_filters:
            if filter == "name":
                fields.append({"label": "Name", "fieldname": "name", "fieldtype": "Data"})
            else:
                field = next((f for f in meta.fields if f.fieldname == filter), None)
                if field:
                    fields.append(field)

    else:
        fields = [field for field in meta.fields if field.in_standard_filter]

    for field in fields:
        options = field.get("options")
        if field.get("fieldtype") == "Select" and options and isinstance(options, str):
            options = options.split("\n")
            options = [{"label": option, "value": option} for option in options]
            if not any([not option.get("value") for option in options]):
                options.insert(0, {"label": "", "value": ""})
        quick_filters.append(
            {
                "label": _(field.get("label")),
                "fieldname": field.get("fieldname"),
                "fieldtype": field.get("fieldtype"),
                "options": options,
            }
        )

    if doctype == "CRM Lead":
        quick_filters = [filter for filter in quick_filters if filter.get("fieldname") != "converted"]

    return quick_filters


@frappe.whitelist(allow_guest=True)
def update_quick_filters(quick_filters: str, old_filters: str, doctype: str):
    quick_filters = json.loads(quick_filters)
    old_filters = json.loads(old_filters)

    new_filters = [filter for filter in quick_filters if filter not in old_filters]
    removed_filters = [filter for filter in old_filters if filter not in quick_filters]

    # update or create global quick filter settings
    create_update_global_settings(doctype, quick_filters)

    # remove old filters
    for filter in removed_filters:
        update_in_standard_filter(filter, doctype, 0)

    # add new filters
    for filter in new_filters:
        update_in_standard_filter(filter, doctype, 1)


def create_update_global_settings(doctype, quick_filters):
    if global_settings := frappe.db.exists("CRM Global Settings", {"dt": doctype, "type": "Quick Filters"}):
        frappe.db.set_value("CRM Global Settings", global_settings, "json", json.dumps(quick_filters))
    else:
        # create CRM Global Settings doc
        doc = frappe.new_doc("CRM Global Settings")
        doc.dt = doctype
        doc.type = "Quick Filters"
        doc.json = json.dumps(quick_filters)
        doc.insert()


def update_in_standard_filter(fieldname, doctype, value):
    if property_name := frappe.db.exists(
        "Property Setter",
        {"doc_type": doctype, "field_name": fieldname, "property": "in_standard_filter"},
    ):
        frappe.db.set_value("Property Setter", property_name, "value", value)
    else:
        make_property_setter(
            doctype,
            fieldname,
            "in_standard_filter",
            value,
            "Check",
            validate_fields_for_doctype=False,
        )


@frappe.whitelist(allow_guest=True)
def get_data(
    doctype=None,
    filters=None,
    order_by=None,
    page_length=20,
    page_length_count=20,
    column_field=None,
    title_field=None,
    columns=None,
    rows=None,
    kanban_columns=None,
    kanban_fields=None,
    view=None,
    default_filters=None,
):
    # ---------- BASIC VALIDATION & NORMALIZATION ----------

    # doctype is mandatory
    if not doctype:
        frappe.throw(_("Missing required parameter: doctype"), frappe.ValidationError)

    # view can come as JSON string
    if view and isinstance(view, str):
        try:
            view = frappe.parse_json(view)
        except Exception:
            view = None

    # normalize filters (can be dict, JSON string, empty, etc.)
    if isinstance(filters, str):
        # JSON string or ""
        filters = frappe.parse_json(filters or "{}")
    elif isinstance(filters, dict):
        filters = filters
    elif filters in (None, "", "null"):
        filters = {}
    else:
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            filters = {}

    filters = frappe._dict(filters)

    # order_by: provide a sane default if not passed
    if not order_by:
        order_by = "modified desc"

    # helpers to normalize list-like params
    def ensure_list(val):
        if isinstance(val, str):
            return frappe.parse_json(val or "[]")
        elif val is None:
            return []
        else:
            return val

    columns = ensure_list(columns)
    rows = ensure_list(rows)
    kanban_columns = ensure_list(kanban_columns)
    kanban_fields = ensure_list(kanban_fields)

    custom_view = False

    # replace @me macros in filters
    for key in list(filters.keys()):
        value = filters[key]
        if isinstance(value, list):
            if "@me" in value:
                value[value.index("@me")] = frappe.session.user
            elif "%@me%" in value:
                idxs = [i for i, v in enumerate(value) if v == "%@me%"]
                for i in idxs:
                    value[i] = "%" + frappe.session.user + "%"
        elif value == "@me":
            filters[key] = frappe.session.user

    # merge default_filters if provided
    if default_filters:
        if isinstance(default_filters, str):
            default_filters = frappe.parse_json(default_filters)
        filters.update(default_filters)

    is_default = True
    data = []
    _list = get_controller(doctype)
    default_rows = []
    if hasattr(_list, "default_list_data"):
        default_rows = _list.default_list_data().get("rows")

    meta = frappe.get_meta(doctype)

    custom_view_name = view.get("custom_view_name") if view else None
    view_type = view.get("view_type") if view else None
    group_by_field = view.get("group_by_field") if view else None

    # ---------- LIST / GROUP VIEW ----------
    if view_type != "kanban":
        # تحديث المهام المتأخرة قبل قراءة البيانات (لـ CRM Task فقط)
        if doctype == "CRM Task":
            try:
                from frappe.utils import now_datetime
                current_dt = now_datetime()
                # تحديث مباشر في قاعدة البيانات
                frappe.db.sql(
                    """
                    UPDATE `tabCRM Task`
                    SET status = 'late'
                    WHERE due_date < %s
                    AND status NOT IN ('Done', 'late')
                    AND due_date IS NOT NULL
                """,
                    (current_dt,),
                    as_dict=False,
                )
                frappe.db.commit()
            except Exception as e:
                frappe.log_error(f"Error updating overdue tasks in list view: {str(e)}")
                pass

        if columns or rows:
            custom_view = True
            is_default = False

        if not columns:
            columns = [
                {"label": "Name", "type": "Data", "key": "name", "width": "16rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ]

        if not rows:
            rows = ["name"]

        default_view_filters = {
            "dt": doctype,
            "type": view_type or "list",
            "is_standard": 1,
            "user": frappe.session.user,
        }

        if not custom_view and frappe.db.exists("CRM View Settings", default_view_filters):
            list_view_settings = frappe.get_doc("CRM View Settings", default_view_filters)
            columns = frappe.parse_json(list_view_settings.columns)
            rows = frappe.parse_json(list_view_settings.rows)
            is_default = False
        elif not custom_view or (is_default and hasattr(_list, "default_list_data")):
            rows = default_rows
            columns = _list.default_list_data().get("columns")

        # ensure rows contains all column keys
        for column in list(columns):
            if column.get("key") not in rows:
                rows.append(column.get("key"))
            column["label"] = _(column.get("label"))

            if column.get("key") == "_liked_by" and column.get("width") == "10rem":
                column["width"] = "50px"

            # remove hidden columns
            column_meta = meta.get_field(column.get("key"))
            if column_meta and column_meta.get("hidden"):
                columns.remove(column)

        # ensure group_by_field is included in rows
        if group_by_field and group_by_field not in rows:
            rows.append(group_by_field)

        # لـ CRM Task: تحديث قاعدة البيانات أولاً ثم قراءة البيانات
        if doctype == "CRM Task":
            from frappe.utils import now_datetime
            current_dt = now_datetime()
            try:
                frappe.db.sql(
                    """
                    UPDATE `tabCRM Task`
                    SET status = 'late'
                    WHERE due_date < %s
                    AND status NOT IN ('Done', 'late')
                    AND due_date IS NOT NULL
                """,
                    (current_dt,),
                )
                frappe.db.commit()
                frappe.clear_cache(doctype="CRM Task")
            except Exception as e:
                frappe.log_error(f"Error updating overdue tasks: {str(e)}")

        data = (
            frappe.get_list(
                doctype,
                fields=rows,
                filters=filters,
                order_by=order_by,
                page_length=page_length,
            )
            or []
        )
        data = parse_list_data(data, doctype)

    # ---------- KANBAN VIEW ----------
    if view_type == "kanban":
        # تحديث المهام المتأخرة قبل قراءة البيانات (لـ CRM Task فقط)
        if doctype == "CRM Task":
            try:
                from frappe.utils import now_datetime
                current_dt = now_datetime()
                frappe.db.sql(
                    """
                    UPDATE `tabCRM Task`
                    SET status = 'late'
                    WHERE due_date < %s
                    AND status NOT IN ('Done', 'late')
                    AND due_date IS NOT NULL
                """,
                    (current_dt,),
                    as_dict=False,
                )
                frappe.db.commit()
                frappe.clear_cache(doctype="CRM Task")
            except Exception as e:
                frappe.log_error(f"Error updating overdue tasks in kanban view: {str(e)}")
                pass

        if not rows:
            rows = default_rows

        if not kanban_columns and column_field:
            field_meta = frappe.get_meta(doctype).get_field(column_field)
            if field_meta.fieldtype == "Link":
                kanban_columns = frappe.get_all(
                    field_meta.options,
                    fields=["name"],
                    order_by="modified asc",
                )
            elif field_meta.fieldtype == "Select":
                kanban_columns = [{"name": option} for option in field_meta.options.split("\n")]

        if not title_field:
            title_field = "name"
            if hasattr(_list, "default_kanban_settings"):
                title_field = _list.default_kanban_settings().get("title_field")

        if title_field not in rows:
            rows.append(title_field)

        if not kanban_fields:
            kanban_fields = ["name"]
            if hasattr(_list, "default_kanban_settings"):
                kanban_fields = json.loads(_list.default_kanban_settings().get("kanban_fields"))

        for field in kanban_fields:
            if field not in rows:
                rows.append(field)

        for kc in kanban_columns:
            # Start with base filters
            column_filters = []

            # Convert and add the main filters first
            if filters:
                base_filters = convert_filter_to_tuple(doctype, filters)
                column_filters.extend(base_filters)

            # Add the column-specific filter
            if column_field and kc.get("name"):
                column_filters.append([doctype, column_field, "=", kc.get("name")])

            order = kc.get("order")
            if kc.get("delete"):
                column_data = []
            else:
                col_page_length = kc.get("page_length", 20)

                if order:
                    column_data = get_records_based_on_order(
                        doctype, rows, column_filters, col_page_length, order
                    )
                else:
                    column_data = frappe.get_list(
                        doctype,
                        fields=rows,
                        filters=column_filters,
                        order_by=order_by,
                        page_length=col_page_length,
                    )

                all_count = frappe.get_list(
                    doctype,
                    filters=column_filters,
                    fields="count(*) as total_count",
                )[0].total_count

                kc["all_count"] = all_count
                kc["count"] = len(column_data)

            if order:
                column_data = sorted(
                    column_data,
                    key=lambda x: order.index(x.get("name")) if x.get("name") in order else len(order),
                )

            data.append({"column": kc, "fields": kanban_fields, "data": column_data})

    # ---------- FIELD META ----------
    fields = frappe.get_meta(doctype).fields
    fields = [field for field in fields if field.fieldtype not in no_value_fields]
    fields = [
        {
            "label": _(field.label),
            "fieldtype": field.fieldtype,
            "fieldname": field.fieldname,
            "options": field.options,
        }
        for field in fields
        if field.label and field.fieldname
    ]

    std_fields = [
        {"label": "Name", "fieldtype": "Data", "fieldname": "name"},
        {"label": "Created On", "fieldtype": "Datetime", "fieldname": "creation"},
        {"label": "Last Modified", "fieldtype": "Datetime", "fieldname": "modified"},
        {
            "label": "Modified By",
            "fieldtype": "Link",
            "fieldname": "modified_by",
            "options": "User",
        },
        {"label": "Assigned To", "fieldtype": "Text", "fieldname": "_assign"},
        {"label": "Owner", "fieldtype": "Link", "fieldname": "owner", "options": "User"},
        {"label": "Like", "fieldtype": "Data", "fieldname": "_liked_by"},
    ]

    for field in std_fields:
        if field.get("fieldname") not in rows:
            rows.append(field.get("fieldname"))
        if field not in fields:
            field["label"] = _(field["label"])
            fields.append(field)

    if not is_default and custom_view_name:
        is_default = frappe.db.get_value("CRM View Settings", custom_view_name, "load_default_columns")

    if group_by_field and view_type == "group_by":

        def get_options(type, options):
            if type == "Select":
                return [option for option in options.split("\n")]
            else:
                has_empty_values = any([not d.get(group_by_field) for d in data])
                opts = list(set([d.get(group_by_field) for d in data]))
                opts = [u for u in opts if u]
                if has_empty_values:
                    opts.append("")

                if order_by and group_by_field in order_by:
                    order_by_fields = order_by.split(",")
                    order_by_fields = [
                        (field.split(" ")[0], field.split(" ")[1]) for field in order_by_fields
                    ]
                    if (group_by_field, "asc") in order_by_fields:
                        opts.sort()
                    elif (group_by_field, "desc") in order_by_fields:
                        opts.sort(reverse=True)
                else:
                    opts.sort()
                return opts

        for field in fields:
            if field.get("fieldname") == group_by_field:
                group_by_field = {
                    "label": field.get("label"),
                    "fieldname": field.get("fieldname"),
                    "fieldtype": field.get("fieldtype"),
                    "options": get_options(field.get("fieldtype"), field.get("options")),
                }

    return {
        "data": data,
        "columns": columns,
        "rows": rows,
        "fields": fields,
        "column_field": column_field,
        "title_field": title_field,
        "kanban_columns": kanban_columns,
        "kanban_fields": kanban_fields,
        "group_by_field": group_by_field,
        "page_length": page_length,
        "page_length_count": page_length_count,
        "is_default": is_default,
        "views": get_views(doctype),
        "total_count": frappe.get_list(
            doctype, filters=filters, fields="count(*) as total_count"
        )[0].total_count,
        "row_count": len(data),
        "form_script": get_form_script(doctype),
        "list_script": get_form_script(doctype, "List"),
        "view_type": view_type,
    }


def parse_list_data(data, doctype):
    _list = get_controller(doctype)
    if hasattr(_list, "parse_list_data"):
        data = _list.parse_list_data(data)
    return data


def convert_filter_to_tuple(doctype, filters):
    if isinstance(filters, dict):
        filters_items = filters.items()
        filters = []
        for key, value in filters_items:
            filters.append(make_filter_tuple(doctype, key, value))
    return filters


def get_records_based_on_order(doctype, rows, filters, page_length, order):
    records = []
    filters = convert_filter_to_tuple(doctype, filters)
    in_filters = filters.copy()
    in_filters.append([doctype, "name", "in", order[:page_length]])
    records = frappe.get_list(
        doctype,
        fields=rows,
        filters=in_filters,
        order_by="creation desc",
        page_length=page_length,
    )

    if len(records) < page_length:
        not_in_filters = filters.copy()
        not_in_filters.append([doctype, "name", "not in", order])
        remaining_records = frappe.get_list(
            doctype,
            fields=rows,
            filters=not_in_filters,
            order_by="creation desc",
            page_length=page_length - len(records),
        )
        for record in remaining_records:
            records.append(record)

    return records


@frappe.whitelist(allow_guest=True)
def get_fields_meta(doctype, restricted_fieldtypes=None, as_array=False, only_required=False):
    not_allowed_fieldtypes = [
        "Tab Break",
        "Section Break",
        "Column Break",
    ]

    if restricted_fieldtypes:
        restricted_fieldtypes = frappe.parse_json(restricted_fieldtypes)
        not_allowed_fieldtypes += restricted_fieldtypes

    fields = frappe.get_meta(doctype).fields
    fields = [field for field in fields if field.fieldtype not in not_allowed_fieldtypes]

    standard_fields = [
        {"fieldname": "name", "fieldtype": "Link", "label": "ID", "options": doctype},
        {"fieldname": "owner", "fieldtype": "Link", "label": "Created By", "options": "User"},
        {
            "fieldname": "modified_by",
            "fieldtype": "Link",
            "label": "Last Updated By",
            "options": "User",
        },
        {"fieldname": "_user_tags", "fieldtype": "Data", "label": "Tags"},
        {"fieldname": "_liked_by", "fieldtype": "Data", "label": "Like"},
        {"fieldname": "_comments", "fieldtype": "Text", "label": "Comments"},
        {"fieldname": "_assign", "fieldtype": "Text", "label": "Assigned To"},
        {"fieldname": "creation", "fieldtype": "Datetime", "label": "Created On"},
        {"fieldname": "modified", "fieldtype": "Datetime", "label": "Last Updated On"},
    ]

    for field in standard_fields:
        if not restricted_fieldtypes or field.get("fieldtype") not in restricted_fieldtypes:
            fields.append(field)

    if only_required:
        fields = [field for field in fields if field.get("reqd")]

    if as_array:
        return fields

    fields_meta = {}
    for field in fields:
        fields_meta[field.get("fieldname")] = field
        if field.get("fieldtype") == "Table":
            _fields = frappe.get_meta(field.get("options")).fields
            fields_meta[field.get("fieldname")] = {"df": field, "fields": _fields}

    return fields_meta


@frappe.whitelist(allow_guest=True)
def remove_assignments(doctype, name, assignees, ignore_permissions=False):
    # Handle both JSON string and already-decoded list
    if isinstance(assignees, str):
        assignees = json.loads(assignees)
    elif not isinstance(assignees, list):
        frappe.throw(_("assignees must be a list or JSON string"))

    if not assignees:
        return

    for assign_to in assignees:
        set_status(
            doctype,
            name,
            todo=None,
            assign_to=assign_to,
            status="Cancelled",
            ignore_permissions=ignore_permissions,
        )


@frappe.whitelist()
def remove_multiple_assignments(doctype, names, ignore_permissions=False):
    """
    Remove all assignments from multiple documents.
    Used when clearing assignments from bulk operations.
    """
    if isinstance(names, str):
        names = json.loads(names)
    elif not isinstance(names, list):
        frappe.throw(_("names must be a list or JSON string"))

    if not names:
        return

    # Get all ToDo records for these documents
    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": ["in", names],
            "status": ["!=", "Cancelled"],
        },
        fields=["name", "allocated_to", "reference_name"],
    )

    # Cancel all ToDo records
    # Cancel all ToDo records
    for todo in todos:
        set_status(
            doctype,
            todo["reference_name"],
            todo=todo["name"],
            assign_to=todo["allocated_to"],
            status="Cancelled",
            ignore_permissions=ignore_permissions,
        )

    return {"ok": True, "count": len(todos)}


@frappe.whitelist(allow_guest=True)
def get_assigned_users(doctype, name, default_assigned_to=None):
    assigned_users = frappe.get_all(
        "ToDo",
        fields=["allocated_to"],
        filters={
            "reference_type": doctype,
            "reference_name": name,
            "status": ("!=", "Cancelled"),
        },
        pluck="allocated_to",
    )

    users = list(set(assigned_users))

    # if users is empty, add default_assigned_to
    if not users and default_assigned_to:
        users = [default_assigned_to]
    return users


# -----------------------------
# FIXED for Frappe v15
# - frappe.has_permission() does NOT accept name=
# - use doc= (Document) for permission check
# - supports both name and names (bulk)
# - accepts assign_to as list / string / JSON string
# - optional ignore_permissions param
# -----------------------------
@frappe.whitelist()
def assign_without_rule(
    doctype: str,
    assign_to,
    name: Optional[str] = None,
    names: Optional[str] = None,
    description: str = "",
    ignore_permissions: bool = False,
    **kwargs,
):
    if not doctype:
        frappe.throw(_("doctype is required"))

    frappe.logger("crm").debug(f"assign_without_rule started: doctype={doctype}, names={names}, assign_to={assign_to}")

    # Normalize assign_to to a list of strings
    if isinstance(assign_to, str):
        try:
            assign_to = frappe.parse_json(assign_to)
        except Exception:
            assign_to = [assign_to]
    if not isinstance(assign_to, list):
        assign_to = [assign_to] if assign_to else []

    users = [str(u) for u in assign_to if u]
    if not users:
        frappe.throw(_("assign_to is required and cannot be empty"))

    # Normalize doc_names to a list of strings
    doc_names = []
    if name:
        doc_names.append(name)
    
    if names:
        if isinstance(names, str):
            try:
                parsed_names = frappe.parse_json(names)
                if isinstance(parsed_names, list):
                    doc_names.extend([str(n) for n in parsed_names if n])
                else:
                    doc_names.append(str(parsed_names))
            except Exception:
                doc_names.append(names)
        elif isinstance(names, list):
            doc_names.extend([str(n) for n in names if n])
        else:
            doc_names.append(str(names))

    # Deduplicate
    doc_names = list(set([n for n in doc_names if n]))

    if not doc_names:
        frappe.throw(_("Document name(s) required (name or names parameter)"), frappe.ValidationError)

    # -------------------------
    # Assign using standard assign_to.add
    # -------------------------
    from frappe.desk.form.assign_to import add as add_assignment

    original_flag = getattr(frappe.flags, "ignore_assign_rule", None)
    frappe.flags.ignore_assign_rule = True

    assigned_count = 0
    skipped_no_permission = 0

    try:
        for doc_name in doc_names:
            if not ignore_permissions:
                if not frappe.has_permission(doctype, "read", doc=doc_name):
                    skipped_no_permission += 1
                    continue

            for user in users:
                try:
                    add_assignment(
                        {
                            "doctype": doctype,
                            "name": doc_name,
                            "assign_to": [user],
                            "description": description or "",
                            "notify": 1,
                        }
                    )
                    assigned_count += 1
                except Exception as e:
                    frappe.log_error(
                        title="assign_without_rule error",
                        message=f"Failed to assign {doctype} {doc_name} to {user}: {str(e)}"
                    )
    except Exception as ge:
        frappe.log_error(frappe.get_traceback(), "assign_without_rule global error")
        raise ge
    finally:
        if original_flag is None:
            if hasattr(frappe.flags, "ignore_assign_rule"):
                delattr(frappe.flags, "ignore_assign_rule")
        else:
            frappe.flags.ignore_assign_rule = original_flag

    return {
        "ok": True,
        "assigned_to": users,
        "assigned_count": assigned_count,
        "skipped_no_permission": skipped_no_permission,
        "doc_names": doc_names,
    }


@frappe.whitelist(allow_guest=True)
def get_fields(doctype: str, allow_all_fieldtypes: bool = False):
    not_allowed_fieldtypes = [*list(frappe.model.no_value_fields), "Read Only"]
    if allow_all_fieldtypes:
        not_allowed_fieldtypes = []
    fields = frappe.get_meta(doctype).fields

    _fields = []

    for field in fields:
        if field.fieldtype not in not_allowed_fieldtypes and field.fieldname:
            _fields.append(field)

    return _fields


def getCounts(d, doctype):
    d["_email_count"] = (
        frappe.db.count(
            "Communication",
            filters={
                "reference_doctype": doctype,
                "reference_name": d.get("name"),
                "communication_type": "Communication",
            },
        )
        or 0
    )
    d["_email_count"] = d["_email_count"] + frappe.db.count(
        "Communication",
        filters={
            "reference_doctype": doctype,
            "reference_name": d.get("name"),
            "communication_type": "Automated Message",
        },
    )
    d["_comment_count"] = frappe.db.count(
        "Comment",
        filters={"reference_doctype": doctype, "reference_name": d.get("name"), "comment_type": "Comment"},
    )
    d["_task_count"] = frappe.db.count(
        "CRM Task", filters={"reference_doctype": doctype, "reference_docname": d.get("name")}
    )
    d["_note_count"] = frappe.db.count(
        "FCRM Note", filters={"reference_doctype": doctype, "reference_docname": d.get("name")}
    )
    return d


@frappe.whitelist(allow_guest=True)
def get_linked_docs_of_document(doctype, docname):
    doc = frappe.get_doc(doctype, docname)
    linked_docs = get_linked_docs(doc)
    dynamic_linked_docs = get_dynamic_linked_docs(doc)

    linked_docs.extend(dynamic_linked_docs)
    linked_docs = list({doc["reference_docname"]: doc for doc in linked_docs}.values())

    docs_data = []
    for doc in linked_docs:
        data = frappe.get_doc(doc["reference_doctype"], doc["reference_docname"])
        title = data.get("title")
        if data.doctype == "CRM Call Log":
            title = f"Call from {data.get('from')} to {data.get('to')}"

        if data.doctype == "CRM Deal":
            title = data.get("organization")

        docs_data.append(
            {
                "doc": data.doctype,
                "title": title or data.get("name"),
                "reference_docname": doc["reference_docname"],
                "reference_doctype": doc["reference_doctype"],
            }
        )
    return docs_data


def remove_doc_link(doctype, docname):
    linked_doc_data = frappe.get_doc(doctype, docname)
    linked_doc_data.update(
        {
            "reference_doctype": None,
            "reference_docname": None,
        }
    )
    linked_doc_data.save(ignore_permissions=True)


def remove_contact_link(doctype, docname):
    linked_doc_data = frappe.get_doc(doctype, docname)
    linked_doc_data.update(
        {
            "contact": None,
            "contacts": [],
        }
    )
    linked_doc_data.save(ignore_permissions=True)


@frappe.whitelist(allow_guest=True)
def remove_linked_doc_reference(items, remove_contact=None, delete=False):
    if isinstance(items, str):
        items = frappe.parse_json(items)

    for item in items:
        if remove_contact:
            remove_contact_link(item["doctype"], item["docname"])
        else:
            remove_doc_link(item["doctype"], item["docname"])

        if delete:
            frappe.delete_doc(item["doctype"], item["docname"])

    return "success"


@frappe.whitelist(allow_guest=True)
def delete_bulk_docs(doctype, items, delete_linked=False):
    from frappe.desk.reportview import delete_bulk

    items = frappe.parse_json(items)
    for doc in items:
        linked_docs = get_linked_docs_of_document(doctype, doc)
        for linked_doc in linked_docs:
            remove_linked_doc_reference(
                [
                    {
                        "doctype": linked_doc["reference_doctype"],
                        "docname": linked_doc["reference_docname"],
                    }
                ],
                remove_contact=doctype == "Contact",
                delete=delete_linked,
            )

    if len(items) > 10:
        frappe.enqueue("frappe.desk.reportview.delete_bulk", doctype=doctype, items=items)
    else:
        delete_bulk(doctype, items)
    return "success"
