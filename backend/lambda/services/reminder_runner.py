"""
Reminder Runner for Ledgerly (WhatsApp + Automation).

Connects existing services:
LedgerService -> ReminderService -> WhatsAppService

Finds customers with CREDIT transactions that are due or overdue,
formats polite reminder messages via ReminderService, and delivers them
via WhatsAppService.
"""

from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Union

from services.ledger_service import LedgerService
from services.reminder_service import ReminderService, parse_date_value
from services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


class ReminderRunner:
    """
    Orchestrates automated debt reminders across existing services.
    Reads customer ledger state, evaluates due/overdue status, and triggers WhatsApp delivery.
    """

    def __init__(
        self,
        ledger_service: Optional[LedgerService] = None,
        reminder_service: Optional[ReminderService] = None,
        whatsapp_service: Optional[WhatsAppService] = None,
        phone_number_id: Optional[str] = None,
    ) -> None:
        self.ledger_service = ledger_service or LedgerService()
        self.reminder_service = reminder_service or ReminderService()
        self.whatsapp_service = whatsapp_service or WhatsAppService()
        self.phone_number_id = phone_number_id

    def run(
        self,
        shop_id: str,
        today: Union[date, datetime, str],
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a reminder run for a given shop and reference date.

        Args:
            shop_id: Unique identifier of the shop.
            today: Reference calendar date (date, datetime, or ISO string) to evaluate against.
            phone_number_id: Optional Meta WhatsApp Phone Number ID to use for sending.

        Returns:
            A summary dictionary containing counts and details:
            - shop_id: str
            - customers_processed: int
            - transactions_checked: int
            - reminders_found: int
            - reminders_sent: int
            - send_failures: int
            - candidates: list of reminder candidates identified
            - details: list of delivery status per candidate
            - errors: list of errors encountered
        """
        # 1. Validate shop_id
        if not shop_id or not isinstance(shop_id, str) or not shop_id.strip():
            raise ValueError("shop_id must be a non-empty string.")
        clean_shop_id = shop_id.strip()

        # 2. Validate and normalize today date
        if today is None:
            raise ValueError("Explicit 'today' date is required.")

        if isinstance(today, datetime):
            eval_today = today.date()
        elif isinstance(today, date):
            eval_today = today
        else:
            eval_today = parse_date_value(today)
            if eval_today is None:
                raise ValueError(f"Invalid 'today' parameter: {today}. Must be a date object or valid date string.")

        active_phone_number_id = phone_number_id or self.phone_number_id

        summary: Dict[str, Any] = {
            "shop_id": clean_shop_id,
            "customers_processed": 0,
            "transactions_checked": 0,
            "reminders_found": 0,
            "reminders_sent": 0,
            "send_failures": 0,
            "candidates": [],
            "details": [],
            "errors": [],
        }

        # 3. Retrieve customers for shop
        try:
            customers = self.ledger_service.list_customers(clean_shop_id)
        except Exception as err:
            logger.error(f"Failed to list customers for shop {clean_shop_id}: {err}")
            summary["errors"].append({
                "shop_id": clean_shop_id,
                "error": f"Failed to list customers: {str(err)}",
            })
            return summary

        if not customers:
            return summary

        # 4. Iterate over customers
        for customer in customers:
            summary["customers_processed"] += 1

            if not isinstance(customer, dict):
                summary["errors"].append({
                    "error": f"Invalid customer record format: {customer}",
                })
                continue

            cust_id = (
                customer.get("customerId")
                or customer.get("customer_id")
                or customer.get("id")
            )
            cust_name = (
                customer.get("name")
                or customer.get("customerName")
                or customer.get("customer_name")
            )
            cust_phone = (
                customer.get("phone")
                or customer.get("phoneNumber")
                or customer.get("phone_number")
            )

            if not cust_id or not str(cust_id).strip():
                summary["errors"].append({
                    "customer": customer,
                    "error": "Customer record missing customerId.",
                })
                continue

            clean_cust_id = str(cust_id).strip()
            clean_cust_phone = str(cust_phone).strip() if cust_phone else ""

            # Retrieve customer transactions
            try:
                transactions = self.ledger_service.get_customer_transactions(clean_cust_id, clean_shop_id)
            except Exception as err:
                logger.error(f"Failed to get transactions for customer {clean_cust_id}: {err}")
                summary["errors"].append({
                    "customer_id": clean_cust_id,
                    "error": f"Failed to retrieve transactions: {str(err)}",
                })
                continue

            if not transactions:
                continue

            # Determine customer outstanding balance: skip if customer has no debt (balance <= 0)
            cust_balance = None
            try:
                bal_val = self.ledger_service.calculate_customer_balance(clean_cust_id, clean_shop_id)
                if isinstance(bal_val, (int, float, Decimal)):
                    cust_balance = bal_val
            except Exception:
                cust_balance = None

            if cust_balance is not None and cust_balance <= 0:
                continue

            # Process each transaction
            for tx in transactions:
                summary["transactions_checked"] += 1

                if not isinstance(tx, dict):
                    continue

                # Create shallow in-memory copy and attach customerName without mutating DB or original tx
                tx_adapted = dict(tx)
                if cust_name:
                    tx_adapted["customerName"] = cust_name

                try:
                    candidate = self.reminder_service.evaluate_transaction(tx_adapted, today=eval_today)
                except Exception as err:
                    logger.error(
                        f"Error evaluating transaction {tx.get('transactionId') or tx.get('id')} for customer {clean_cust_id}: {err}"
                    )
                    summary["errors"].append({
                        "customer_id": clean_cust_id,
                        "transaction_id": tx.get("transactionId") or tx.get("id"),
                        "error": f"Failed to evaluate transaction: {str(err)}",
                    })
                    continue

                if candidate is None:
                    continue

                summary["reminders_found"] += 1

                # Record candidate details with customer context
                candidate_record = dict(candidate)
                candidate_record["customer_id"] = clean_cust_id
                candidate_record["phone"] = clean_cust_phone
                summary["candidates"].append(candidate_record)

                # Send WhatsApp reminder
                if not clean_cust_phone:
                    summary["send_failures"] += 1
                    error_msg = f"Customer {clean_cust_id} ({cust_name or 'unknown'}) is missing a phone number."
                    logger.warning(error_msg)
                    summary["details"].append({
                        "customer_id": clean_cust_id,
                        "phone": "",
                        "transaction_id": candidate.get("transaction_id"),
                        "status": candidate.get("status"),
                        "sent": False,
                        "error": error_msg,
                    })
                    summary["errors"].append({
                        "customer_id": clean_cust_id,
                        "transaction_id": candidate.get("transaction_id"),
                        "error": error_msg,
                    })
                    continue

                try:
                    send_resp = self.whatsapp_service.send_text(
                        to=clean_cust_phone,
                        text=candidate["message"],
                        phone_number_id=active_phone_number_id,
                    )
                    summary["reminders_sent"] += 1
                    summary["details"].append({
                        "customer_id": clean_cust_id,
                        "phone": clean_cust_phone,
                        "transaction_id": candidate.get("transaction_id"),
                        "status": candidate.get("status"),
                        "sent": True,
                        "response": send_resp,
                    })
                except Exception as err:
                    summary["send_failures"] += 1
                    logger.error(f"WhatsApp send failed for customer {clean_cust_id} ({clean_cust_phone}): {err}")
                    summary["details"].append({
                        "customer_id": clean_cust_id,
                        "phone": clean_cust_phone,
                        "transaction_id": candidate.get("transaction_id"),
                        "status": candidate.get("status"),
                        "sent": False,
                        "error": str(err),
                    })
                    summary["errors"].append({
                        "customer_id": clean_cust_id,
                        "phone": clean_cust_phone,
                        "transaction_id": candidate.get("transaction_id"),
                        "error": f"WhatsApp send failed: {str(err)}",
                    })

        return summary
