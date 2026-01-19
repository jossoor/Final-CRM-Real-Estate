# apps/crm/crm/api/reminders.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, now

# ----------------------------
# Utilities & Permission checks
# ----------------------------

def _has_column(dt: str, col: str) -> bool:
    try:
        return bool(frappe.db.has_column(dt, col))
    except Exception:
        return False


def _can_read(doctype: str, name: str, user: str | None = None) -> bool:
    """Check read permission for a given user (defaults to session user)."""
    try:
        doc = frappe.get_doc(doctype, name)
    except frappe.DoesNotExistError:
        return False
    return bool(doc.has_permission("read", user=user))


def _ensure_can_read(doctype: str, name: str, user: str | None = None) -> None:
    """Strict check: raise PermissionError if user cannot read the doc."""
    if not _can_read(doctype, name, user=user):
        frappe.throw(
            _("Not permitted to access {0} {1}").format(doctype, name),
            frappe.PermissionError,
        )


def _coerce_datetime(value: str):
    if not value:
        frappe.throw(_("remind_at is required"))
    try:
        return get_datetime(value)
    except Exception:
        frappe.throw(_("Invalid datetime format for remind_at: {0}").format(value))


# ----------------------------
# Dynamic schema resolvers
# ----------------------------

REMINDER_DT = "Reminder"
DELAYED_BATCH_LIMIT = 200

def _reminder_schema():
    """ارجع السكيمة الحالية لجدول Reminder ديناميكيًا"""
    ref_dt = "reference_doctype" if _has_column(REMINDER_DT, "reference_doctype") else "reminder_doctype"
    ref_nm = "reference_name"    if _has_column(REMINDER_DT, "reference_name")    else "reminder_docname"
    return {
        "ref_dt": ref_dt,
        "ref_nm": ref_nm,
        "has_status":   _has_column(REMINDER_DT, "status"),
        "has_comment":  _has_column(REMINDER_DT, "comment"),
        "has_done":     _has_column(REMINDER_DT, "done"),
        "has_notified": _has_column(REMINDER_DT, "notified"),
        "has_descr":    _has_column(REMINDER_DT, "description"),
        "has_user":     _has_column(REMINDER_DT, "user"),
        "has_creation": _has_column(REMINDER_DT, "creation"),
    }

def _comment_delay_field() -> str | None:
    """
    رجّع اسم عمود علامة التأخير في Comment:
    - عندك الحقل اسمه 'delayed' بالفعل.
    """
    return "delayed" if _has_column("Comment", "delayed") else None


# -----------------------
# Realtime/Notification helpers
# -----------------------

def _notify_in_crm(*, for_user: str, subject: str, doctype: str, name: str, content: str = "", notif_type: str = "Alert") -> str:
    log = frappe.get_doc(
        {
            "doctype": "Notification Log",
            "for_user": for_user,
            "subject": subject,
            "email_content": content or subject,
            "type": notif_type,
            "document_type": doctype,
            "document_name": name,
            "from_user": frappe.session.user if frappe.session.user else "Administrator",
            "date": now(),
        }
    ).insert(ignore_permissions=True)

    frappe.publish_realtime(
        event="notification",
        message={"name": log.name},
        user=for_user,
        after_commit=True,
    )
    return log.name


# -------------
# CRUD Endpoints (Reminders)
# -------------

@frappe.whitelist()
def add_reminder(doctype: str, name: str, remind_at: str, description: str, comment: str | None = None):
    if frappe.session.user == "Guest":
        frappe.only_for(("System Manager", "Administrator"), allow_roles=False)

    _ensure_can_read(doctype, name)
    schema = _reminder_schema()

    dt = _coerce_datetime(remind_at)
    if dt < now_datetime():
        frappe.throw(_("Remind at must be in the future"))
    if not description or not description.strip():
        frappe.throw(_("Description is required"))

    data = {
        "doctype": REMINDER_DT,
        schema["ref_dt"]: doctype,
        schema["ref_nm"]: name,
        "remind_at": dt,
        "description": description.strip(),
        "user": frappe.session.user,
    }
    if schema["has_status"]:
        data["status"] = "Open"
    if comment and schema["has_comment"]:
        data["comment"] = comment
    if schema["has_done"]:
        data["done"] = 0

    r = frappe.get_doc(data).insert(ignore_permissions=False)
    return {"name": r.name}


def _augment_status(rows: list[dict]) -> list[dict]:
    """لو مافيش status، ارجعه مشتق من notified."""
    schema = _reminder_schema()
    if schema["has_status"]:
        return rows
    for r in rows:
        r["status"] = "Sent" if r.get("notified") else "Pending"
    return rows


@frappe.whitelist()
def list_reminders(doctype: str, name: str):
    _ensure_can_read(doctype, name)
    schema = _reminder_schema()

    fields = ["name", "remind_at"]
    if schema["has_descr"]: fields.append("description")
    if schema["has_creation"]: fields.append("creation")
    if schema["has_user"]: fields.append("user")
    if schema["has_status"]:
        fields.append("status")
    elif schema["has_notified"]:
        fields.append("notified")
    if schema["has_comment"]:
        fields.append("comment")
    if schema["has_done"]:
        fields.append("done")

    filters = {
        schema["ref_dt"]: doctype,
        schema["ref_nm"]: name,
        "user": frappe.session.user,
    }
    if schema["has_status"]:
        filters["status"] = ["in", ["Open", "Scheduled"]]

    rows = frappe.get_all(
        REMINDER_DT,
        filters=filters,
        fields=fields,
        order_by="remind_at asc, creation asc",
    )
    return _augment_status(rows)


@frappe.whitelist()
def list_for_doc(doctype: str, name: str):
    """
    تُستخدم في Leads list وغيرها لعرض التذكيرات المرتبطة بالمستند.
    لو اليوزر مالوش صلاحية Read على الـ doc → نرجّع [] بدل PermissionError.
    """
    if not _can_read(doctype, name):
        return []

    schema = _reminder_schema()

    fields = ["name", "remind_at"]
    if schema["has_descr"]:    fields.append("description")
    if schema["has_user"]:     fields.append("user")
    if schema["has_creation"]: fields.append("creation")
    if schema["has_status"]:
        fields.append("status")
    elif schema["has_notified"]:
        fields.append("notified")
    if schema["has_comment"]:  fields.append("comment")
    if schema["has_done"]:     fields.append("done")

    rows = frappe.get_all(
        REMINDER_DT,
        filters={schema["ref_dt"]: doctype, schema["ref_nm"]: name},
        fields=fields,
        order_by="remind_at asc, creation asc",
    )
    return _augment_status(rows)


@frappe.whitelist()
def delete_reminder(reminder_name: str):
    r = frappe.get_doc(REMINDER_DT, reminder_name)
    if r.user == frappe.session.user or frappe.has_permission(REMINDER_DT, "delete"):
        r.delete()
        return True
    frappe.throw(_("Not permitted to delete this reminder"), frappe.PermissionError)


@frappe.whitelist()
def notify_now_for_reminder(reminder_name: str) -> dict:
    schema = _reminder_schema()
    r = frappe.get_doc(REMINDER_DT, reminder_name)
    if r.user != frappe.session.user and not frappe.has_permission(REMINDER_DT, "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    desc = (r.description or "").strip()
    subject = _('Follow-up: "{0}"').format((desc[:60] + ("…" if len(desc) > 60 else "")))

    _notify_in_crm(
        for_user=r.user,
        subject=subject,
        doctype=getattr(r, schema["ref_dt"]),
        name=getattr(r, schema["ref_nm"]),
        content=desc,
    )

    try:
        if schema["has_status"]:
            r.db_set("status", "Sent", update_modified=False)
    except Exception:
        frappe.log_error("Failed to set Reminder status to Sent", "notify_now_for_reminder")
    return {"ok": True}


@frappe.whitelist()
def republish_notification(notification_log_name: str, user: str | None = None) -> dict:
    if not frappe.has_permission("Notification Log", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    log = frappe.get_doc("Notification Log", notification_log_name)
    target_user = user or getattr(log, "for_user", None) or log.owner

    frappe.publish_realtime(
        event="notification",
        message={"name": log.name},
        user=target_user,
        after_commit=True,
    )
    return {"ok": True}


# -----------------------------
# Delayed flag on Comments (NEW)
# -----------------------------

def _set_comment_delay_flag(
    doctype: str, name: str, *, value: int, user: str | None = None
) -> int:
    """
    عيّن قيمة delayed على كومنتات المستند (اختياريًا لمستخدم معيّن).
    يرجّع عدد الصفوف التي تم تعديلها.
    """
    col = _comment_delay_field()
    if not col:
        return 0

    query = [
        "UPDATE `tabComment`",
        f"SET `{col}`=%s",
        "WHERE reference_doctype=%s",
        "  AND reference_name=%s",
        "  AND comment_type='Comment'",
    ]
    params = [value, doctype, name]
    if user:
        query.append("  AND owner=%s")
        params.append(user)

    frappe.db.sql("\n".join(query), tuple(params))
    try:
        return int(getattr(frappe.db._cursor, "rowcount", 0))
    except Exception:
        return 0


def _set_doc_delayed_flag(doctype: str, name: str, value: int) -> None:
    """Update the parent document delayed flag when applicable."""
    if doctype != "CRM Lead":
        return
    if not _has_column("CRM Lead", "delayed"):
        return
    frappe.db.set_value(doctype, name, "delayed", int(bool(value)), update_modified=False)


@frappe.whitelist()
def clear_delayed_flags(doctype: str, name: str) -> dict:
    """
    نظّف كل علامات الـ delayed على كومنتات المستخدم لهذا المستند.
    استدعِها بعد إضافة كومنت + Reminder جديد.
    """
    _ensure_can_read(doctype, name)
    changed = _set_comment_delay_flag(doctype, name, value=0)
    _set_doc_delayed_flag(doctype, name, 0)
    return {"cleared": changed}


@frappe.whitelist()
def mark_overdue_comment(doctype: str, name: str) -> dict:
    """
    لو عندي Reminder متأخر (remind_at < الآن) للمستخدم على نفس المستند
    ولم تتم إضافة كومنت أحدث من موعد التذكير → علّم آخر كومنت للمستخدم كـ delayed=1.
    لو جدول Comment مافهوش عمود delayed → لا شيء (No-op).
    """
    _ensure_can_read(doctype, name)
    col = _comment_delay_field()
    if not col:
        return {"updated": 0, "reason": "no_delayed_column"}

    schema = _reminder_schema()
    user = frappe.session.user

    # 1) آخر Reminder "مفتوح/مجدول" قبل الآن على نفس المستند (strict: < now)
    reminder_filters = {
        schema["ref_dt"]: doctype,
        schema["ref_nm"]: name,
    }
    if schema["has_status"]:
        reminder_filters["status"] = ["in", ["Open", "Scheduled"]]

    overdue = frappe.get_all(
        REMINDER_DT,
        filters=reminder_filters | {"remind_at": ("<", now_datetime())},
        fields=["name", "remind_at"],
        order_by="remind_at desc",
        limit=1,
    )
    if not overdue:
        # مفيش متأخر
        return {"updated": 0, "reason": "no_overdue_reminder"}

    r_at = overdue[0]["remind_at"]

    # 2) آخر كومنت على نفس المستند (بغض النظر عن المالك)
    last_comment = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": doctype,
            "reference_name": name,
            "comment_type": "Comment",
        },
        fields=["name", "creation"],
        order_by="creation desc",
        limit=1,
    )
    if not last_comment:
        # مفيش كومنتات
        return {"updated": 0, "reason": "no_user_comments"}

    c = last_comment[0]
    # 3) لو آخر كومنت أقدم من موعد التذكير → اعتبره متأخر
    if c["creation"] and c["creation"] < r_at:
        frappe.db.set_value("Comment", c["name"], col, 1, update_modified=False)
        return {"updated": 1, "comment": c["name"]}

    return {"updated": 0, "reason": "comment_is_newer_than_reminder"}


# -----------------------------
# Helper endpoints for Delayed flow (NEW)
# -----------------------------

@frappe.whitelist()
def latest_overdue_reminder(doctype: str, name: str):
    """
    يرجّع آخر Reminder متأخر (remind_at < now) بحالة Open/Scheduled لنفس المستخدم على المستند.
    """
    _ensure_can_read(doctype, name)
    schema = _reminder_schema()
    
    # Use SQL to handle NULL status (treat NULL as Open)
    # Check if status column actually exists in DB
    status_cond = ""
    if schema["has_status"] and frappe.db.has_column("Reminder", "status"):
        status_cond = " AND (status IN ('Open', 'Scheduled') OR status IS NULL)"
    
    query = f"""
        SELECT name, remind_at, description
        FROM `tabReminder`
        WHERE `{schema['ref_dt']}` = %s
          AND `{schema['ref_nm']}` = %s
          AND remind_at < %s
          {status_cond}
        ORDER BY remind_at DESC
        LIMIT 1
    """
    
    rows = frappe.db.sql(
        query,
        (doctype, name, now_datetime()),
        as_dict=1,
    )
    return rows[0] if rows else None


@frappe.whitelist()
def recalc_delayed_for_doc(doctype: str, name: str) -> dict:
    """
    أعد حساب Delayed على أحدث تعليق للمستخدم الحالي وفق القاعدة:
    - لو مفيش Reminder متأخر → مسح كل delayed=0.
    - لو فيه Reminder متأخر بموعد r_at:
        * آخر تعليق للمستخدم c:
            - لو c.creation < r_at → علم c.delayed=1 (وباقي تعليقات المستخدم =0).
            - غير كده → امسح أي delayed=0.
    """
    _ensure_can_read(doctype, name)
    col = _comment_delay_field()

    overdue = latest_overdue_reminder(doctype, name)
    if not overdue:
        cleared = _set_comment_delay_flag(doctype, name, value=0)
        _set_doc_delayed_flag(doctype, name, 0)
        return {
            "updated": 0,
            "cleared": cleared,
            "reason": "no_overdue_reminder",
            "delayed": 0,
        }

    r_at = overdue["remind_at"]

    last_comment = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": doctype,
            "reference_name": name,
            "comment_type": "Comment",
        },
        fields=["name", "creation"],
        order_by="creation desc",
        limit=1,
    )

    if not last_comment:
        cleared = _set_comment_delay_flag(doctype, name, value=0)
        _set_doc_delayed_flag(doctype, name, 0)
        return {
            "updated": 0,
            "cleared": cleared,
            "reason": "no_user_comments",
            "overdue_at": r_at,
            "delayed": 0,
        }

    c = last_comment[0]
    _set_comment_delay_flag(doctype, name, value=0)

    is_delayed = 1 if c["creation"] and c["creation"] < r_at else 0

    if col and is_delayed:
        frappe.db.set_value("Comment", c["name"], col, 1, update_modified=False)

    _set_doc_delayed_flag(doctype, name, is_delayed)

    if is_delayed:
        return {"updated": 1, "comment": c["name"], "overdue_at": r_at, "delayed": 1}

    return {
        "updated": 0,
        "reason": "comment_is_newer_than_reminder",
        "overdue_at": r_at,
        "delayed": 0,
    }


# -----------------------------
# Doc Event helpers (Comments & Reminders)
# -----------------------------

def _is_supported_reference(doctype: str) -> bool:
    """Currently flag Delayed only for CRM Lead comments."""
    return doctype == "CRM Lead"


def recalc_from_comment(doc, method=None):
    """
    Doc-event hook: بعد إدراج تعليق Lead جديد، أعِد حساب حالة Delayed.
    """
    try:
        if getattr(doc, "comment_type", None) != "Comment":
            return
        ref_dt = getattr(doc, "reference_doctype", None)
        ref_nm = getattr(doc, "reference_name", None)
        if not ref_dt or not ref_nm or not _is_supported_reference(ref_dt):
            return

        recalc_delayed_for_doc(ref_dt, ref_nm)
    except frappe.PermissionError:
        # تجاهل بهدوء لو اليوزر ماعندوش صلاحية القراءة
        pass
    except Exception:
        frappe.log_error(frappe.get_traceback(), "recalc_from_comment failed")


def recalc_from_reminder(doc, method=None):
    """
    Doc-event hook: أي تعديل/إدراج/حذف على Reminder يفرض إعادة الحساب.
    """
    try:
        schema = _reminder_schema()
        ref_dt = getattr(doc, schema["ref_dt"], None)
        ref_nm = getattr(doc, schema["ref_nm"], None)
        if not ref_dt or not ref_nm or not _is_supported_reference(ref_dt):
            return

        recalc_delayed_for_doc(ref_dt, ref_nm)
    except frappe.PermissionError:
        # تجاهل لو اليوزر المعني ماعندوش قراءة على المستند
        pass
    except Exception:
        frappe.log_error(frappe.get_traceback(), "recalc_from_reminder failed")


def flag_overdue_comments_for_leads(limit: int = 200) -> dict:
    """
    تُستدعى دوريًا (من الـ scheduler) لتحديث حقول delayed على تعليقات الـ Lead
    بناءً على كل التذكيرات المتأخرة المفتوحة.
    """
    schema = _reminder_schema()
    filters = {
        schema["ref_dt"]: "CRM Lead",
        "remind_at": ("<", now_datetime()),
    }
    if schema["has_status"]:
        filters["status"] = ["in", ["Open", "Scheduled"]]

    rows = frappe.get_all(
        REMINDER_DT,
        filters=filters,
        fields=[schema["ref_nm"]],
        order_by="remind_at asc",
        limit=limit,
    )

    leads = []
    for row in rows:
        lead_name = row.get(schema["ref_nm"])
        if not lead_name or lead_name in leads:
            continue
        leads.append(lead_name)

    processed = 0
    for lead_name in leads:
        try:
            recalc_delayed_for_doc("CRM Lead", lead_name)
            processed += 1
        except frappe.PermissionError:
            continue
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"flag_overdue_comments_for_leads: {lead_name}")

    return {"processed": processed, "leads": leads}


@frappe.whitelist()
def get_delayed_map(lead_names: str | list):
    """
    API للواجهة: يرجع خريطة بحالة "متأخر" لكل Lead مقدمة (حتى 200 اسم في الطلب).
    - لو عمود `Comment.delayed` موجود، يستخدمه (سريع) بعد حصر الـ Leads التي لدى المستخدم
      الحالي Reminder متأخر عليها.
    - وإلا يحسبها runtime بمقارنة آخر Reminder متأخر مع آخر Comment.
    - يحترم صلاحيات القراءة للمستخدم الحالي.
    """
    import json
    try:
        if isinstance(lead_names, str):
            try:
                names = json.loads(lead_names)
            except json.JSONDecodeError:
                frappe.throw(_("Invalid list of lead names provided."))
        else:
            names = lead_names

        if not names:
            return {}

        unique_names = []
        seen = set()
        for name in names:
            if not name or name in seen:
                continue
            seen.add(name)
            unique_names.append(name)

        if len(unique_names) > DELAYED_BATCH_LIMIT:
            frappe.throw(
                _("You can request at most {0} leads at once (received {1}).").format(
                    DELAYED_BATCH_LIMIT, len(unique_names)
                )
            )

        readable_leads = [
            name
            for name in unique_names
            if frappe.has_permission("CRM Lead", "read", doc=name)
        ]
        if not readable_leads:
            return {}

        delayed_map = {name: 0 for name in readable_leads}

        schema = _reminder_schema()
        now = now_datetime()
        params = {"leads": readable_leads, "now": now}
        where_clauses = [
            f"`{schema['ref_dt']}` = 'CRM Lead'",
            f"`{schema['ref_nm']}` IN %(leads)s",
            "`remind_at` < %(now)s",
        ]

        if schema.get("has_user"):
            params["user"] = frappe.session.user
            where_clauses.append("`user` = %(user)s")
        if schema.get("has_status"):
            params["statuses"] = ["Open", "Scheduled"]
            where_clauses.append("`status` IN %(statuses)s")

        reminders_query = f"""
            SELECT `{schema['ref_nm']}` AS name, MAX(`remind_at`) AS latest_remind_at
            FROM `tab{REMINDER_DT}`
            WHERE {' AND '.join(where_clauses)}
            GROUP BY `{schema['ref_nm']}`
        """
        latest_reminders = frappe.db.sql(reminders_query, params, as_dict=True)
        reminders_map = {row.name: row.latest_remind_at for row in latest_reminders}

        if not reminders_map:
            return delayed_map

        leads_with_reminders = list(reminders_map.keys())
        col = _comment_delay_field()

        if col:
            comment_rows = frappe.db.sql(
                f"""
                SELECT `reference_name` AS name, MAX(`{col}`) AS is_delayed
                FROM `tabComment`
                WHERE `reference_doctype` = 'CRM Lead'
                  AND `reference_name` IN %(leads)s
                  AND `comment_type` = 'Comment'
                GROUP BY `reference_name`
                """,
                {"leads": leads_with_reminders},
                as_dict=True,
            )
            delayed_from_comments = {row.name: bool(row.is_delayed) for row in comment_rows}

            for lead_name in leads_with_reminders:
                if delayed_from_comments.get(lead_name):
                    delayed_map[lead_name] = 1
            return delayed_map

        latest_comments = frappe.db.sql(
            """
            SELECT `reference_name` AS name, MAX(`creation`) AS latest_comment_at
            FROM `tabComment`
            WHERE `reference_doctype` = 'CRM Lead'
              AND `reference_name` IN %(leads)s
              AND `comment_type` = 'Comment'
            GROUP BY `reference_name`
            """,
            {"leads": leads_with_reminders},
            as_dict=True,
        )
        comments_map = {row.name: row.latest_comment_at for row in latest_comments}

        for lead_name in leads_with_reminders:
            reminder_date = reminders_map.get(lead_name)
            comment_date = comments_map.get(lead_name)
            if reminder_date and (not comment_date or comment_date < reminder_date):
                delayed_map[lead_name] = 1

        return delayed_map
    except Exception as e:
        frappe.log_error(title="get_delayed_map failure", message=frappe.get_traceback())
        raise e
