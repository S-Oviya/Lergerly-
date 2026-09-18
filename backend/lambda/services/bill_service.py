"""
Bill representation and message generation service for Ledgerly (Person 2 - Automation / WhatsApp).
Responsible ONLY for generating WhatsApp-ready bill representations from structured transaction data.

STRICT BOUNDARIES:
- Does NOT calculate customer balances (Person 1 / ledger_service responsibility).
- Does NOT query DynamoDB (Person 1 / DynamoDB layer responsibility).
- Does NOT invoke Bedrock (Person 1 / bedrock_service responsibility).
- Does NOT make live Meta WhatsApp Cloud API calls (future integration point).
"""

from typing import Any, Dict, Optional, Union
from services.message_templates import (
    TemplateValidationError,
    format_inr,
    render_payment_confirmation,
    render_transaction_confirmation,
)


class BillService:
    """
    Service responsible for converting structured transaction records into
    WhatsApp-ready bill representations.
    """

    def __init__(self, default_shop_name: str = "Ledgerly") -> None:
        self.default_shop_name = default_shop_name

    def generate_bill(self, transaction: Dict[str, Any]) -> str:
        """
        Generate a WhatsApp-ready bill/transaction confirmation text representation
        from a structured transaction dictionary.

        Accepts standard transaction fields in either camelCase (API/frontend)
        or snake_case (Python backend):
        - customerName / customer_name: customer display name
        - type / transactionType / transaction_type / tx_type: 'CREDIT' or 'PAYMENT'
        - amount: numeric transaction amount (INR)
        - description / itemsNote / items_note / item: optional item/description note
        - dueDate / due_date: optional payment due date string

        Returns:
            WhatsApp-ready text representation of the transaction bill.

        Raises:
            TemplateValidationError: if required fields are missing or invalid.
        """
        if not isinstance(transaction, dict):
            raise TemplateValidationError("Transaction data must be a dictionary.")

        customer_name = (
            transaction.get("customerName")
            or transaction.get("customer_name")
            or transaction.get("name")
        )
        if not customer_name:
            raise TemplateValidationError("Missing required customer name in transaction data.")

        tx_type = (
            transaction.get("type")
            or transaction.get("transactionType")
            or transaction.get("transaction_type")
            or transaction.get("tx_type")
        )
        if not tx_type:
            raise TemplateValidationError("Missing required transaction type ('CREDIT' or 'PAYMENT').")

        amount = transaction.get("amount")
        if amount is None:
            raise TemplateValidationError("Missing required transaction amount.")

        description = (
            transaction.get("description")
            or transaction.get("itemsNote")
            or transaction.get("items_note")
            or transaction.get("item")
            or ""
        )

        due_date = transaction.get("dueDate") or transaction.get("due_date")

        return render_transaction_confirmation(
            customer_name=str(customer_name),
            transaction_type=str(tx_type),
            amount=amount,
            description=str(description) if description else "",
            due_date=str(due_date) if due_date else None,
        )

    def generate_payment_receipt(
        self,
        payment: Union[Dict[str, Any], str],
        amount: Optional[Any] = None,
        reference_id: Optional[str] = None,
    ) -> str:
        """
        Generate a WhatsApp-ready payment receipt message.

        Can be called with:
        - A dictionary: generate_payment_receipt({"customerName": "Rahul", "amount": 500})
        - Positional arguments: generate_payment_receipt("Rahul", 500, reference_id="rec_123")
        """
        if isinstance(payment, dict):
            cust_name = (
                payment.get("customerName")
                or payment.get("customer_name")
                or payment.get("name")
                or ""
            )
            pay_amount = payment.get("amount")
            ref_id = payment.get("referenceId") or payment.get("reference_id") or payment.get("transactionId") or payment.get("transaction_id")
            return render_payment_confirmation(
                customer_name=str(cust_name),
                amount=pay_amount,
                reference_id=str(ref_id) if ref_id else None,
            )

        return render_payment_confirmation(
            customer_name=str(payment),
            amount=amount,
            reference_id=reference_id,
        )

    def format_bill_details(
        self,
        customer_name: str,
        transaction_type: str,
        amount: Any,
        description: Optional[str] = "",
        due_date: Optional[str] = None,
    ) -> str:
        """
        Convenience method to format a bill directly from explicit arguments.
        """
        return render_transaction_confirmation(
            customer_name=customer_name,
            transaction_type=transaction_type,
            amount=amount,
            description=description,
            due_date=due_date,
        )
