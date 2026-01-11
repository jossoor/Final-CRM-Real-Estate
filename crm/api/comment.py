# apps/crm/crm/api/comment.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _
from bs4 import BeautifulSoup
from frappe.utils import now_datetime, strip_html

from crm.fcrm.doctype.crm_notification.crm_notification import notify_user

# -----------------------------------
# Hooks
# -----------------------------------

def on_update(self, method=None):
    """
    - إشعار المنشنز في محتوى التعليق.
    - إدارة وسم التأخير delayed تلقائيًا:
        * mark_overdue_comment: يعلّم آخر كومنت كمتأخر لو فيه Reminder متأخر.
        * clear_delayed_flags: ينضّف الوسم لو الكومنت الحالي أحدث من موعد آخر Reminder متأخر
          أو لو مفيش أصلاً Reminder متأخر.
    """
    # إشعارات المنشنز
    notify_mentions(self)
    
    # تحديث حقل last_comment في الـ Lead
    update_lead_last_comment(self)

    # منطق delayed مربوط فقط على تعليقات "Comment" المرتبطة بمستند
    try:
        if getattr(self, "comment_type", None) != "Comment":
            return
        if not getattr(self, "reference_doctype", None) or not getattr(self, "reference_name", None):
            return

        doctype = self.reference_doctype
        name = self.reference_name

        # استدعاءات الـ Reminder API
        from crm.api import reminders as rapi  # الاستيراد هنا لتجنب الدورات

        # 1) جرّب تمييز المتأخر لو فيه overdue reminder
        try:
            rapi.mark_overdue_comment(doctype, name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "comment.on_update -> mark_overdue_comment")

        # 2) لو الكومنت الحالي أحدث من آخر overdue reminder → امسح أي delayed قديم
        try:
            schema = rapi._reminder_schema()
            reminder_filters = {
                schema["ref_dt"]: doctype,
                schema["ref_nm"]: name,
                "user": frappe.session.user,
            }
            if schema["has_status"]:
                reminder_filters["status"] = ["in", ["Open", "Scheduled"]]

            overdue = frappe.get_all(
                rapi.REMINDER_DT,
                filters=reminder_filters | {"remind_at": ("<=", now_datetime())},
                fields=["name", "remind_at"],
                order_by="remind_at desc",
                limit=1,
            )
            if overdue:
                r_at = overdue[0]["remind_at"]
                if getattr(self, "creation", None) and self.creation >= r_at:
                    # الكومنت أحدث من موعد آخر تذكير متأخر ⇒ نظّف الوسوم
                    rapi.clear_delayed_flags(doctype, name)
            else:
                # مفيش متأخر خالص ⇒ نظّف أي delayed قديم
                rapi.clear_delayed_flags(doctype, name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "comment.on_update -> clear_delayed_flags")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "comment.on_update (outer)")


# -----------------------------------
# Mentions
# -----------------------------------

def notify_mentions(doc):
    """
    استخراج المنشنز من content (HTML) وإرسال إشعارات لهم.
    """
    content = getattr(doc, "content", None)
    if not content:
        return

    mentions = extract_mentions(content)
    if not mentions:
        return

    reference_doc = frappe.get_doc(doc.reference_doctype, doc.reference_name)
    for mention in mentions:
        owner = frappe.get_cached_value("User", doc.owner, "full_name")
        doctype = doc.reference_doctype
        if doctype.startswith("CRM "):
            doctype = doctype[4:].lower()
        name = (
            reference_doc.lead_name
            if doctype == "lead"
            else reference_doc.organization or reference_doc.lead_name
        )
        notification_text = f"""
            <div class="mb-2 leading-5 text-ink-gray-5">
                <span class="font-medium text-ink-gray-9">{ owner }</span>
                <span>{ _('mentioned you in {0}').format(doctype) }</span>
                <span class="font-medium text-ink-gray-9">{ name }</span>
            </div>
        """
        notify_user(
            {
                "owner": doc.owner,
                "assigned_to": mention.email,
                "notification_type": "Mention",
                "message": doc.content,
                "notification_text": notification_text,
                "reference_doctype": "Comment",
                "reference_docname": doc.name,
                "redirect_to_doctype": doc.reference_doctype,
                "redirect_to_docname": doc.reference_name,
            }
        )


def extract_mentions(html):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    mentions = []
    for d in soup.find_all("span", attrs={"data-type": "mention"}):
        mentions.append(
            frappe._dict(full_name=d.get("data-label"), email=d.get("data-id"))
        )
    return mentions


# -----------------------------------
# Attachments
# -----------------------------------

@frappe.whitelist()
def add_attachments(name: str, attachments: Iterable[str | dict]) -> None:
    """Add attachments to the given Comment

    :param name: Comment name
    :param attachments: File names or dicts with keys "fname" and "fcontent"
    """
    for a in attachments:
        if isinstance(a, str):
            attach = frappe.db.get_value(
                "File", {"name": a}, ["file_url", "is_private"], as_dict=1
            )
            if not attach:
                continue
            file_args = {
                "file_url": attach.file_url,
                "is_private": attach.is_private,
            }
        elif isinstance(a, dict) and "fcontent" in a and "fname" in a:
            file_args = {
                "file_name": a["fname"],
                "content": a["fcontent"],
                "is_private": 1,
            }
        else:
            continue

        file_args.update(
            {
                "attached_to_doctype": "Comment",
                "attached_to_name": name,
                "folder": "Home/Attachments",
            }
        )

        _file = frappe.new_doc("File")
        _file.update(file_args)
        _file.save(ignore_permissions=True)


def update_lead_last_comment(doc):
    """
    Update last_comment field in CRM Lead when a comment is added
    """
    try:
        if doc.reference_doctype != "CRM Lead" or not doc.reference_name:
            return

        # Ensure we're dealing with a Comment type
        if doc.comment_type != "Comment":
            return

        content = doc.content
        if not content:
            return

        # Strip HTML tags
        clean_content = strip_html(content)
        
        # Truncate if necessary (Small Text is usually 65535 chars, but good to be safe for display)
        if len(clean_content) > 140:
             clean_content = clean_content[:137] + "..."

        frappe.db.set_value("CRM Lead", doc.reference_name, "last_comment", clean_content)
        
    except Exception:
        frappe.log_error(frappe.get_traceback(), "update_lead_last_comment failed")

