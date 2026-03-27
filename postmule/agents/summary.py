"""
Daily summary agent — builds and sends the daily summary email.

Sends:
  1. Immediate URGENT alert if any ForwardToMe items were found.
  2. Daily summary email with all processed mail, bills, API usage.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.agents.summary")


def send_urgent_alert(
    smtp_config: dict[str, Any],
    alert_email: str,
    forward_to_me_items: list[dict[str, Any]],
) -> None:
    """
    Send an immediate URGENT alert when ForwardToMe items are detected.
    Called during the run (not just at end of day).
    """
    if not forward_to_me_items:
        return

    subject = f"[PostMule URGENT] {len(forward_to_me_items)} item(s) need physical forwarding"
    lines = ["<b>Action required: Contact your virtual mailbox to forward these items.</b><br><br>"]
    for item in forward_to_me_items:
        lines.append(
            f"&bull; <b>{item.get('sender', 'Unknown sender')}</b> — {item.get('summary', '')}<br>"
            f"&nbsp;&nbsp;Received: {item.get('date_received', '')}<br><br>"
        )

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;padding:20px;">
      <div style="background:#C62828;color:white;padding:12px 16px;border-radius:6px;margin-bottom:16px;">
        <b>URGENT: Physical Mail Requires Forwarding</b>
      </div>
      {"".join(lines)}
      <p style="color:#5A7090;font-size:12px;">PostMule &mdash; {date.today().isoformat()}</p>
    </div>
    """
    _send_email(smtp_config, alert_email, subject, html)
    log.info(f"Sent URGENT ForwardToMe alert for {len(forward_to_me_items)} item(s)")


def send_daily_summary(
    smtp_config: dict[str, Any],
    alert_email: str,
    run_stats: dict[str, Any],
    processed_items: list[dict[str, Any]],
    pending_bills: list[dict[str, Any]],
    api_usage: dict[str, Any],
    dry_run: bool = False,
) -> None:
    """
    Send the daily summary email.

    Args:
        smtp_config:     SMTP connection details from credentials.
        alert_email:     Recipient address.
        run_stats:       Dict with counts (bills, notices, etc.).
        processed_items: List of all ProcessedMail dicts from today's run.
        pending_bills:   Bills not yet matched to a bank transaction.
        api_usage:       API safety agent summary dict.
        dry_run:         Log but don't send.
    """
    today = date.today().isoformat()
    subject = f"[PostMule] Daily Summary — {today}"

    if dry_run:
        log.info(f"[DRY RUN] Would send daily summary to {alert_email}")
        return

    html = _build_summary_html(today, run_stats, processed_items, pending_bills, api_usage)
    _send_email(smtp_config, alert_email, subject, html)
    log.info(f"Daily summary sent to {alert_email}")


def _build_summary_html(
    today: str,
    stats: dict,
    items: list[dict],
    pending_bills: list[dict],
    api_usage: dict,
) -> str:
    from jinja2 import Environment, FileSystemLoader
    template_dir = Path(__file__).parent.parent / "web" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("email_daily.html")
    context = _build_email_context(today, stats, items, pending_bills, api_usage)
    return template.render(**context)


def _build_email_context(
    today: str,
    stats: dict,
    items: list[dict],
    pending_bills: list[dict],
    api_usage: dict,
) -> dict:
    from datetime import date as _date

    # Fall back to len(items) when pdfs_processed is absent (e.g. in tests or
    # partial stats dicts), so is_quiet and section rendering stay correct.
    total = stats.get("pdfs_processed", len(items))
    try:
        d = _date.fromisoformat(today)
    except ValueError:
        d = _date.today()
    today_label = d.strftime(f"%A, %B {d.day}, %Y")

    # Summary subtitle: "2 bills · 1 notice · 1 forward to you"
    sub_parts: list[str] = []
    for key, singular, plural in [
        ("bills", "bill", "bills"),
        ("notices", "notice", "notices"),
        ("forward_to_me", "forward to you", "forwards to you"),
        ("junk", "junk", "junk"),
        ("needs_review", "needs review", "need review"),
    ]:
        n = stats.get(key, 0)
        if n:
            sub_parts.append(f"{n} {singular if n == 1 else plural}")
    summary_sub = " · ".join(sub_parts)

    # Badge styles (inline — CSS classes not reliable across all email clients)
    _BADGE: dict[str, tuple[str, str]] = {
        "bill":    ("Bill",          "background-color:#FFF3CD;color:#7A5C00;border:1px solid #F0C850;"),
        "notice":  ("Notice",        "background-color:#E8F0FC;color:#1E4A8A;border:1px solid #C0D4F4;"),
        "forward": ("Forward To Me", "background-color:#FCE8E8;color:#8A1A1A;border:1px solid #F4C0C0;"),
        "overdue": ("Overdue Bill",  "background-color:#FCE8E8;color:#C62828;border:1px solid #F4C0C0;"),
        "other":   ("Other",         "background-color:#F0F2F5;color:#5A7090;border:1px solid #D0D8E4;"),
    }
    _CAT_BADGE: dict[str, str] = {
        "Bill": "bill", "Notice": "notice", "ForwardToMe": "forward",
        "Personal": "other", "Junk": "other", "NeedsReview": "other",
    }

    # Action Required: ForwardToMe processed items + overdue pending bills
    action_items: list[dict] = []
    for item in items:
        if item.get("category") == "ForwardToMe":
            parts = [p for p in [item.get("summary"), f"Received {item['processed_date']}" if item.get("processed_date") else None] if p]
            label, style = _BADGE["forward"]
            action_items.append({
                "badge_label": label, "badge_style": style, "urgent": True,
                "sender": item.get("sender", "Unknown"),
                "detail": " · ".join(parts),
                "amount": None,
            })

    remaining_pending: list[dict] = []
    for bill in pending_bills:
        days = _days_until(bill.get("due_date", ""))
        if days is not None and days < 0:
            n = abs(days)
            label, style = _BADGE["overdue"]
            action_items.append({
                "badge_label": label, "badge_style": style, "urgent": False,
                "sender": bill.get("sender", ""),
                "detail": f"Due {bill.get('due_date', '')} — {n} day{'s' if n != 1 else ''} overdue",
                "amount": bill.get("amount_due"),
            })
        else:
            remaining_pending.append(bill)

    # New Items: all processed items sorted by category
    new_items: list[dict] = []
    for item in sorted(items, key=lambda x: x.get("category", "")):
        cat = item.get("category", "")
        badge_key = _CAT_BADGE.get(cat, "other")
        badge_label, badge_style = _BADGE[badge_key]

        if cat == "Bill":
            parts: list[str] = []
            if item.get("processed_date"):
                parts.append(f"Received {item['processed_date']}")
            days = _days_until(item.get("due_date", ""))
            if item.get("due_date"):
                if days is None or days < 0:
                    parts.append(f"Due {item['due_date']}")
                elif days == 0:
                    parts.append("Due today")
                elif days == 1:
                    parts.append(f"Due {item['due_date']} · due tomorrow")
                else:
                    parts.append(f"Due {item['due_date']} · {days} days remaining")
            detail = " · ".join(parts)
        else:
            detail_parts = [p for p in [item.get("summary"), f"Received {item['processed_date']}" if item.get("processed_date") else None] if p]
            detail = " · ".join(detail_parts)

        new_items.append({
            "badge_label": badge_label, "badge_style": badge_style,
            "sender": item.get("sender", "Unknown"),
            "detail": detail,
            "amount": item.get("amount_due") if cat == "Bill" else None,
            "amount_overdue": False,
        })

    # API usage summary line
    req_pct = 0
    if api_usage.get("request_limit"):
        req_pct = int(api_usage.get("requests", 0) / api_usage["request_limit"] * 100)
    provider = api_usage.get("provider", "LLM").capitalize()
    api_summary = (
        f"{provider} API: {api_usage.get('requests', 0):,}/{api_usage.get('request_limit', 1400):,}"
        f" requests ({req_pct}%)"
        f" — {api_usage.get('tokens', 0):,}/{api_usage.get('token_limit', 900000):,} tokens"
        f" — Est. cost: ${api_usage.get('estimated_cost_usd', 0):.4f}"
    )

    return {
        "today": today,
        "today_label": today_label,
        "total": total,
        "is_quiet": total == 0 and not action_items and not remaining_pending,
        "summary_sub": summary_sub,
        "action_items": action_items,
        "new_items": new_items,
        "pending_items": remaining_pending,
        "run_ok": stats.get("status") == "success",
        "run_errors": stats.get("errors", 0),
        "api_summary": api_summary,
        "dashboard_url": "http://localhost:5000",
    }


def send_bill_due_alert(
    smtp_config: dict[str, Any],
    alert_email: str,
    all_bills: list[dict[str, Any]],
    alert_days: int = 7,
    dry_run: bool = False,
    data_dir: Path | None = None,
    alert_interval_days: int = 3,
) -> None:
    """
    Send a proactive alert for bills due within *alert_days* days.
    Only sends if upcoming bills exist. Skips already-paid bills.
    Won't re-alert for the same bill within *alert_interval_days* days.
    """
    upcoming = []
    for bill in all_bills:
        if bill.get("status") in ("paid", "matched"):
            continue
        days = _days_until(bill.get("due_date", ""))
        if days is None or not (0 <= days <= alert_days):
            continue
        last_alerted = bill.get("alert_sent_date")
        if last_alerted:
            try:
                days_since = (date.today() - date.fromisoformat(last_alerted)).days
                if days_since < alert_interval_days:
                    continue
            except ValueError:
                pass
        upcoming.append((days, bill))

    if not upcoming:
        return

    upcoming.sort(key=lambda x: x[0])
    subject = f"[PostMule] {len(upcoming)} bill(s) due within {alert_days} days"

    rows = ""
    for days_left, bill in upcoming:
        urgency = "#C62828" if days_left <= 3 else "#E8A020"
        due_label = "Today" if days_left == 0 else f"in {days_left}d"
        rows += (
            f'<tr>'
            f'<td style="padding:8px 14px;color:#0F2044;">{bill.get("sender","")}</td>'
            f'<td style="padding:8px 14px;color:#0F2044;">${bill.get("amount_due",0):.2f}</td>'
            f'<td style="padding:8px 14px;color:{urgency};font-weight:600;">'
            f'{bill.get("due_date","")} ({due_label})</td>'
            f'</tr>'
        )

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;padding:20px;">
      <div style="background:#0F2044;color:white;padding:12px 16px;border-radius:6px;margin-bottom:16px;">
        <b>Post<span style="color:#E8A020;">Mule</span></b>
        &nbsp;&mdash;&nbsp;Bills Due Soon
      </div>
      <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;border:1px solid #DDE3EC;">
        <tr style="background:#F5F6F8;">
          <th style="padding:6px 14px;text-align:left;font-size:11px;color:#5A7090;">Sender</th>
          <th style="padding:6px 14px;text-align:left;font-size:11px;color:#5A7090;">Amount</th>
          <th style="padding:6px 14px;text-align:left;font-size:11px;color:#5A7090;">Due</th>
        </tr>
        {rows}
      </table>
      <p style="color:#5A7090;font-size:12px;margin-top:12px;">PostMule &mdash; {date.today().isoformat()}</p>
    </div>
    """

    if dry_run:
        log.info(f"[DRY RUN] Would send bill due alert ({len(upcoming)} bills) to {alert_email}")
        return

    _send_email(smtp_config, alert_email, subject, html)
    log.info(f"Sent bill due alert for {len(upcoming)} bill(s) due within {alert_days} days")

    if data_dir:
        from postmule.data import bills as _bills_data
        for _, bill in upcoming:
            if bill.get("id"):
                _bills_data.mark_bill_alerted(data_dir, bill["id"])


def _pending_bills_section(rows_html: str) -> str:
    return f"""
    <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;margin-bottom:12px;overflow:hidden;">
      <div style="padding:10px 14px;font-size:10px;font-weight:600;letter-spacing:2px;color:#7A90A8;text-transform:uppercase;border-bottom:1px solid #DDE3EC;">
        Pending Bills
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <tr style="background:#F5F6F8;">
          <th style="padding:6px 14px;text-align:left;font-size:11px;color:#5A7090;">Sender</th>
          <th style="padding:6px 14px;text-align:left;font-size:11px;color:#5A7090;">Amount</th>
          <th style="padding:6px 14px;text-align:left;font-size:11px;color:#5A7090;">Due</th>
        </tr>
        {rows_html}
      </table>
    </div>
    """


def _days_until(due_date_str: str) -> int | None:
    if not due_date_str:
        return None
    try:
        due = date.fromisoformat(due_date_str)
        return (due - date.today()).days
    except ValueError:
        return None


def _html_to_text(html: str) -> str:
    """Minimal HTML → plain text for the text/plain fallback part."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&mdash;", "—", text)
    text = re.sub(r"&bull;", "•", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _send_email(smtp_config: dict[str, Any], to_address: str, subject: str, html: str) -> None:
    """Send an HTML email with a plain-text fallback via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_config.get("from_address", to_address)
    msg["To"] = to_address
    msg.attach(MIMEText(_html_to_text(html), "plain"))
    msg.attach(MIMEText(html, "html"))

    host = smtp_config.get("host", "smtp.gmail.com")
    port = int(smtp_config.get("port", 587))
    username = smtp_config.get("username", "")
    password = smtp_config.get("password", "")

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(username, password)
        server.sendmail(msg["From"], [to_address], msg.as_string())
