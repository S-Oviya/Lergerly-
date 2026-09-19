"""
Customer-facing payment reminder WhatsApp message templates for Ledgerly (WhatsApp + Automation).

Responsible ONLY for generating polite, customer-facing reminder text.
Strict boundary: Does NOT calculate balances, interest, or financial state.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Union

from services.message_templates import TemplateValidationError, format_inr


class ReminderValidationError(ValueError):
    """Raised when reminder inputs fail validation (e.g. empty name, invalid date, non-positive amount)."""
    pass


def validate_and_format_date(due_date: Union[date, datetime, str]) -> str:
    """
    Validates a due date and formats it as a clean WhatsApp string (e.g. '20 Sep 2026').
    Raises ReminderValidationError if the date is invalid, empty, or unparseable.
    """
    if due_date is None:
        raise ReminderValidationError("Due date cannot be None.")

    if isinstance(due_date, datetime):
        return due_date.strftime("%d %b %Y")

    if isinstance(due_date, date):
        return due_date.strftime("%d %b %Y")

    if isinstance(due_date, str):
        trimmed = due_date.strip()
        if not trimmed:
            raise ReminderValidationError("Due date cannot be empty.")

        # Try common date formats
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(trimmed, fmt).date()
                return parsed.strftime("%d %b %Y")
            except ValueError:
                continue

        # Try ISO format
        try:
            parsed = date.fromisoformat(trimmed)
            return parsed.strftime("%d %b %Y")
        except ValueError:
            pass

        raise ReminderValidationError(f"Invalid due date format: '{due_date}'. Must be a valid date string.")

    raise ReminderValidationError(f"Invalid due date type: {type(due_date).__name__}. Expected date, datetime, or str.")


def render_due_reminder(
    customer_name: str,
    amount: Union[int, float, Decimal, str],
    due_date: Union[date, datetime, str],
) -> str:
    """
    Generate a polite WhatsApp payment reminder for a payment due today.

    Example output:
    Ledgerly

    Payment reminder

    Hi Rahul,

    Your payment of ₹500 is due today.

    Due date: 20 Sep 2026

    Please make the payment when convenient.
    """
    if not customer_name or not isinstance(customer_name, str) or not customer_name.strip():
        raise ReminderValidationError("Customer name is required and cannot be empty.")

    clean_customer = customer_name.strip()

    try:
        formatted_amount = format_inr(amount)
    except (TemplateValidationError, ValueError) as err:
        raise ReminderValidationError(f"Invalid reminder amount: {err}") from err

    formatted_date = validate_and_format_date(due_date)

    lines = [
        "Ledgerly",
        "",
        "Payment reminder",
        "",
        f"Hi {clean_customer},",
        "",
        f"Your payment of {formatted_amount} is due today.",
        "",
        f"Due date: {formatted_date}",
        "",
        "Please make the payment when convenient.",
    ]

    return "\n".join(lines)


def render_overdue_reminder(
    customer_name: str,
    amount: Union[int, float, Decimal, str],
    due_date: Union[date, datetime, str],
    days_overdue: int,
) -> str:
    """
    Generate a polite WhatsApp payment reminder for an overdue payment.

    Example output:
    Ledgerly

    Payment reminder

    Hi Rahul,

    A payment of ₹500 was due on 20 Sep 2026.

    It is now 3 days overdue.

    Please make the payment when convenient.
    """
    if not customer_name or not isinstance(customer_name, str) or not customer_name.strip():
        raise ReminderValidationError("Customer name is required and cannot be empty.")

    clean_customer = customer_name.strip()

    try:
        formatted_amount = format_inr(amount)
    except (TemplateValidationError, ValueError) as err:
        raise ReminderValidationError(f"Invalid reminder amount: {err}") from err

    formatted_date = validate_and_format_date(due_date)

    if days_overdue is None or isinstance(days_overdue, bool):
        raise ReminderValidationError("Days overdue must be a valid integer.")

    if isinstance(days_overdue, float):
        if not days_overdue.is_integer():
            raise ReminderValidationError(f"Days overdue must be an integer, got float {days_overdue}.")
        days_overdue = int(days_overdue)
    elif not isinstance(days_overdue, int):
        raise ReminderValidationError(f"Days overdue must be an integer, got {type(days_overdue).__name__}.")

    if days_overdue <= 0:
        raise ReminderValidationError(f"Days overdue must be a positive integer greater than zero, got {days_overdue}.")

    unit = "day" if days_overdue == 1 else "days"

    lines = [
        "Ledgerly",
        "",
        "Payment reminder",
        "",
        f"Hi {clean_customer},",
        "",
        f"A payment of {formatted_amount} was due on {formatted_date}.",
        "",
        f"It is now {days_overdue} {unit} overdue.",
        "",
        "Please make the payment when convenient.",
    ]

    return "\n".join(lines)
