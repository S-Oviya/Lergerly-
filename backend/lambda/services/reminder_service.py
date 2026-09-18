"""
Reminder automation service for Ledgerly.
Belongs to Person 2 (WhatsApp + Automation).

Responsible ONLY for determining whether supplied transaction records require a reminder
and formatting the corresponding WhatsApp reminder candidate.

STRICT BOUNDARIES:
- Does NOT calculate customer balances (Person 1 responsibility).
- Does NOT query DynamoDB or any database (Person 1 responsibility).
- Does NOT call Bedrock or any LLM (Person 1 responsibility).
- Does NOT call Meta / WhatsApp API (future transport milestone).
- Operates entirely in-memory on data passed into it with an explicit injected 'today' date.
"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Union

from services.reminder_templates import (
    ReminderValidationError,
    render_due_reminder,
    render_overdue_reminder,
)


def parse_date_value(date_val: Any) -> Optional[date]:
    """
    Safely parse a date, datetime, or date string into a datetime.date object.
    Returns None if date_val is empty, invalid, or cannot be parsed.
    """
    if date_val is None:
        return None

    if isinstance(date_val, datetime):
        return date_val.date()

    if isinstance(date_val, date):
        return date_val

    if isinstance(date_val, str):
        trimmed = date_val.strip()
        if not trimmed:
            return None

        # Common format attempts
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(trimmed, fmt).date()
            except ValueError:
                continue

        # ISO format attempt
        try:
            return date.fromisoformat(trimmed)
        except ValueError:
            return None

    return None


class ReminderService:
    """
    Evaluates already-structured transaction records to produce WhatsApp payment reminder candidates.
    Never calculates balances; treats each supplied record independently.
    """

    def __init__(self) -> None:
        pass

    def evaluate_transaction(
        self,
        transaction: Dict[str, Any],
        today: date,
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates a single transaction record against an explicit today date.

        Rules:
        - Non-dict or invalid records -> None (handled cleanly)
        - Payment records (type != 'CREDIT') -> None
        - Missing or invalid due date -> None
        - Same-day duplicate (lastReminderDate == today) -> None
        - due_date > today (future) -> None
        - due_date == today -> DUE reminder candidate
        - due_date < today -> OVERDUE reminder candidate with days_overdue

        Returns:
            Dictionary with transaction details, reminder status, and WhatsApp text, or None.
        """
        if not isinstance(transaction, dict):
            return None

        # 1. Require explicit today date (never default to system clock)
        if today is None:
            raise ReminderValidationError("Explicit 'today' date is required.")

        if isinstance(today, datetime):
            eval_today = today.date()
        elif isinstance(today, date):
            eval_today = today
        else:
            parsed_today = parse_date_value(today)
            if parsed_today is None:
                raise ReminderValidationError(f"Invalid 'today' parameter: {today}. Must be a date object.")
            eval_today = parsed_today

        # 2. Filter out payment records - only credit transactions have money due
        tx_type = (
            transaction.get("type")
            or transaction.get("transactionType")
            or transaction.get("transaction_type")
            or transaction.get("tx_type")
            or ""
        )
        norm_type = str(tx_type).strip().upper()
        if norm_type != "CREDIT":
            return None

        # 3. Extract and validate customer name
        customer_name = (
            transaction.get("customerName")
            or transaction.get("customer_name")
            or transaction.get("name")
        )
        if not customer_name or not isinstance(customer_name, str) or not customer_name.strip():
            return None

        clean_customer = customer_name.strip()

        # 4. Extract and validate amount
        amount = transaction.get("amount")
        if amount is None:
            return None

        try:
            float_amt = float(amount)
            if float_amt <= 0:
                return None
        except (ValueError, TypeError):
            return None

        # 5. Extract and parse due date
        due_date_raw = transaction.get("dueDate") or transaction.get("due_date")
        if not due_date_raw:
            return None

        due_date_obj = parse_date_value(due_date_raw)
        if due_date_obj is None:
            return None

        # 6. Duplicate reminder protection
        last_reminder_raw = transaction.get("lastReminderDate") or transaction.get("last_reminder_date")
        if last_reminder_raw:
            last_reminder_obj = parse_date_value(last_reminder_raw)
            if last_reminder_obj is not None and last_reminder_obj == eval_today:
                # Already notified today on this calendar date
                return None

        # 7. Extract transaction identifier
        tx_id = (
            transaction.get("id")
            or transaction.get("transactionId")
            or transaction.get("transaction_id")
            or ""
        )

        # 8. Date evaluation
        if due_date_obj > eval_today:
            # Future due date -> No reminder needed yet
            return None

        elif due_date_obj == eval_today:
            # Payment is due today
            try:
                msg_text = render_due_reminder(
                    customer_name=clean_customer,
                    amount=amount,
                    due_date=due_date_raw,
                )
            except ReminderValidationError:
                return None

            return {
                "transaction_id": str(tx_id),
                "customer_name": clean_customer,
                "amount": amount,
                "due_date": str(due_date_raw),
                "status": "DUE",
                "message": msg_text,
            }

        else:
            # Payment is overdue
            days_overdue = (eval_today - due_date_obj).days

            try:
                msg_text = render_overdue_reminder(
                    customer_name=clean_customer,
                    amount=amount,
                    due_date=due_date_raw,
                    days_overdue=days_overdue,
                )
            except ReminderValidationError:
                return None

            return {
                "transaction_id": str(tx_id),
                "customer_name": clean_customer,
                "amount": amount,
                "due_date": str(due_date_raw),
                "status": "OVERDUE",
                "days_overdue": days_overdue,
                "message": msg_text,
            }

    def process_transactions(
        self,
        transactions: Iterable[Dict[str, Any]],
        today: date,
    ) -> List[Dict[str, Any]]:
        """
        Evaluates multiple transaction records independently.

        Returns a list of reminder candidates.
        Does NOT combine balances across multiple transactions or group by customer.
        """
        if not transactions:
            return []

        reminders: List[Dict[str, Any]] = []
        for tx in transactions:
            try:
                candidate = self.evaluate_transaction(tx, today=today)
                if candidate is not None:
                    reminders.append(candidate)
            except Exception:
                # Handle unexpected corrupt records cleanly
                continue

        return reminders
