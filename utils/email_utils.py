from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence, Tuple

"""Helper routines for sending Outlook emails via COM.

Requires the optional ``pywin32`` package; install it with ``pip install pywin32`` on Windows.
"""

try:  # pywin32 is optional so Streamlit can still boot without Outlook
    import win32com.client as win32
except ImportError as import_error:
    win32 = None
    _IMPORT_ERROR = import_error


def _resolve_account(outlook, preferred_sender: str):
    """Find an Outlook account that matches the preferred sender address/name."""
    preferred = preferred_sender.strip().lower()
    try:
        accounts = outlook.Session.Accounts
    except AttributeError as exc:  # pragma: no cover - COM specific
        raise RuntimeError("Không truy cập được danh sách account Outlook.") from exc

    for idx in range(1, accounts.Count + 1):
        account = accounts.Item(idx)
        smtp_address = getattr(account, "SmtpAddress", "") or ""
        display_name = getattr(account, "DisplayName", "") or ""
        if smtp_address.lower() == preferred or display_name.lower() == preferred:
            return account
    raise RuntimeError(f"Không tìm thấy tài khoản Outlook '{preferred_sender}'.")


def send_outlook_email(
    recipients: Sequence[str],
    subject: str,
    body: str,
    attachments: Iterable[Path] | None = None,
    preferred_sender: str | None = None,
) -> Tuple[str, str]:
    if not recipients:
        raise ValueError("At least one recipient email is required.")

    if win32 is None:  # pragma: no cover - env-specific guard
        raise ImportError(
            "pywin32 is not installed. Install it with 'pip install pywin32' on Windows."
        ) from _IMPORT_ERROR

    outlook = win32.Dispatch("Outlook.Application")
    mail = outlook.CreateItem(0)

    if preferred_sender:
        account = _resolve_account(outlook, preferred_sender)
        try:
            mail.SendUsingAccount = account
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Không thể thiết lập account Outlook '{preferred_sender}'."
            ) from exc

    recipients_str = ";".join(recipients)
    mail.To = recipients_str
    mail.Subject = subject
    mail.Body = body

    if attachments:
        for attachment in attachments:
            mail.Attachments.Add(str(attachment))

    # Lấy địa chỉ email người gửi
    sender_address = ""
    sender_account = getattr(mail, "SendUsingAccount", None)
    if sender_account:
        # Thử lấy SmtpAddress trước
        sender_address = getattr(sender_account, "SmtpAddress", "")
        # Nếu không có, thử CurrentUser
        if not sender_address:
            sender_address = getattr(sender_account, "CurrentUser", {}).get("Address", "")
        # Nếu vẫn không có, dùng DisplayName
        if not sender_address:
            sender_address = getattr(sender_account, "DisplayName", "")
    
    # Nếu vẫn không có, thử lấy từ mail object
    if not sender_address:
        sender_address = getattr(mail, "SenderEmailAddress", "")
    
    # Nếu vẫn không có và có preferred_sender, dùng nó
    if not sender_address and preferred_sender:
        sender_address = preferred_sender

    try:
        mail.Send()
        
        # Force send/receive to ensure email is sent immediately
        try:
            namespace = outlook.GetNamespace("MAPI")
            namespace.SendAndReceive(False)  # False = don't show progress dialog
        except:
            pass  # SendAndReceive might not be available in all Outlook versions
            
    finally:
        # Accessing mail.To after Send() can raise COM errors, so reuse cached string.
        print(
            f"Outlook send request → From: {sender_address or 'unknown'} | To: {recipients_str} | Subject: {subject}"
        )

    return sender_address or "", recipients_str
