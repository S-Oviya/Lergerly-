"""
Reusable WhatsApp message templates for Ledgerly (Person 2 - Automation / WhatsApp).
Pure deterministic functions generating WhatsApp-ready text representations.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union


class TemplateValidationError(ValueError):
    """Raised when template inputs fail validation (e.g. invalid amount or type)."""
    pass


def format_inr(amount: Union[int, float, Decimal, str]) -> str:
    """
    Format a numeric amount as an Indian Rupee (INR) currency string (e.g. ₹500, ₹1,250.50).
    Strictly validates that amount is a positive numeric value > 0.
    """
    if amount is None:
        raise TemplateValidationError("Amount cannot be None.")

    try:
        # Convert to string first to handle floats safely without precision artifacts
        dec = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as err:
        raise TemplateValidationError(f"Invalid amount value '{amount}': must be numeric.") from err

    if dec.is_nan() or dec.is_infinite():
        raise TemplateValidationError("Amount cannot be NaN or Infinite.")

    if dec <= Decimal("0.00"):
        raise TemplateValidationError(f"Amount must be greater than zero, got {dec}.")

    # Format integer amounts without unnecessary decimal places (e.g. ₹500)
    # Format fractional amounts with two decimal places (e.g. ₹500.50)
    if dec == dec.to_integral():
        int_val = int(dec)
        formatted_num = f"{int_val:,}"
    else:
        formatted_num = f"{dec:,.2f}"

    return f"₹{formatted_num}"


def render_transaction_confirmation(
    customer_name: str,
    transaction_type: str,
    amount: Union[int, float, Decimal, str],
    description: Optional[str] = "",
    due_date: Optional[str] = None,
) -> str:
    """
    Generate a WhatsApp-ready transaction confirmation text message.

    Inputs:
    - customer_name: non-empty customer name string
    - transaction_type: 'CREDIT' or 'PAYMENT' (case-insensitive)
    - amount: positive numeric amount
    - description: optional item/note description
    - due_date: optional promise/due date string
    """
    if not customer_name or not isinstance(customer_name, str) or not customer_name.strip():
        raise TemplateValidationError("Customer name is required and cannot be empty.")

    if not transaction_type or not isinstance(transaction_type, str):
        raise TemplateValidationError("Transaction type must be a string ('CREDIT' or 'PAYMENT').")

    norm_type = transaction_type.strip().upper()
    if norm_type not in ("CREDIT", "PAYMENT"):
        raise TemplateValidationError(
            f"Invalid transaction type '{transaction_type}'. Expected 'CREDIT' or 'PAYMENT'."
        )

    formatted_amount = format_inr(amount)
    status_display = "Credit" if norm_type == "CREDIT" else "Payment"

    clean_customer = customer_name.strip()
    clean_desc = description.strip() if isinstance(description, str) else ""
    clean_due = due_date.strip() if isinstance(due_date, str) else None

    lines = [
        "Ledgerly",
        "Transaction recorded",
        "",
        f"Customer: {clean_customer}",
    ]

    if clean_desc:
        lines.append(f"Item: {clean_desc}")

    lines.append(f"Amount: {formatted_amount}")
    lines.append(f"Status: {status_display}")

    if clean_due:
        lines.append(f"Due date: {clean_due}")

    return "\n".join(lines)


def render_payment_confirmation(
    customer_name: str,
    amount: Union[int, float, Decimal, str],
    reference_id: Optional[str] = None,
) -> str:
    """
    Generate a WhatsApp-ready payment confirmation text message.

    Inputs:
    - customer_name: non-empty customer name string
    - amount: positive numeric amount paid
    - reference_id: optional payment reference/receipt ID
    """
    if not customer_name or not isinstance(customer_name, str) or not customer_name.strip():
        raise TemplateValidationError("Customer name is required and cannot be empty.")

    formatted_amount = format_inr(amount)
    clean_customer = customer_name.strip()

    lines = [
        "Ledgerly",
        "Payment recorded",
        "",
        f"Customer: {clean_customer}",
        f"Amount paid: {formatted_amount}",
    ]

    if reference_id and str(reference_id).strip():
        lines.append(f"Receipt ID: {str(reference_id).strip()}")

    return "\n".join(lines)
