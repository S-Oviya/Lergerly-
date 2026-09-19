"""
Unit tests for ReminderRunner (WhatsApp + Automation).
Tests the orchestration of LedgerService -> ReminderService -> WhatsAppService.

Uses mocks/fakes so tests do NOT require AWS credentials, DynamoDB, Meta WhatsApp API, or network access.
"""

from datetime import date, datetime
import os
import sys
import unittest
from unittest.mock import MagicMock, call

# Ensure backend/lambda is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

from services.reminder_runner import ReminderRunner
from services.reminder_service import ReminderService
from services.whatsapp_service import WhatsAppUnavailableError


class TestReminderRunner(unittest.TestCase):
    """Unit tests for ReminderRunner."""

    def setUp(self):
        self.mock_ledger = MagicMock()
        self.mock_whatsapp = MagicMock()
        self.reminder_service = ReminderService()
        self.runner = ReminderRunner(
            ledger_service=self.mock_ledger,
            reminder_service=self.reminder_service,
            whatsapp_service=self.mock_whatsapp,
        )
        self.today = date(2026, 9, 20)

    def test_due_today_credit_generates_and_sends_reminder(self):
        """1. Due-today CREDIT transaction generates and sends a reminder."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-1", "name": "Rahul Sharma", "phone": "+919876543210"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [
            {
                "transactionId": "tx-101",
                "customerId": "cust-1",
                "type": "CREDIT",
                "amount": 500,
                "dueDate": "2026-09-20",
            }
        ]
        self.mock_whatsapp.send_text.return_value = {"messages": [{"id": "wamid-101"}]}

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["customers_processed"], 1)
        self.assertEqual(summary["transactions_checked"], 1)
        self.assertEqual(summary["reminders_found"], 1)
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertEqual(summary["send_failures"], 0)

        # Check candidate details
        self.assertEqual(len(summary["candidates"]), 1)
        candidate = summary["candidates"][0]
        self.assertEqual(candidate["transaction_id"], "tx-101")
        self.assertEqual(candidate["status"], "DUE")
        self.assertEqual(candidate["customer_name"], "Rahul Sharma")
        self.assertIn("Your payment of ₹500 is due today.", candidate["message"])

        # Check delivery
        self.mock_whatsapp.send_text.assert_called_once()
        args, kwargs = self.mock_whatsapp.send_text.call_args
        self.assertEqual(kwargs["to"], "+919876543210")
        self.assertIn("Your payment of ₹500 is due today.", kwargs["text"])

    def test_overdue_credit_generates_and_sends_reminder(self):
        """2. Overdue CREDIT transaction generates and sends a reminder."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-2", "name": "Priya Verma", "phone": "+919876543211"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [
            {
                "transactionId": "tx-202",
                "customerId": "cust-2",
                "type": "CREDIT",
                "amount": 1200,
                "dueDate": "2026-09-17",  # 3 days overdue relative to 2026-09-20
            }
        ]
        self.mock_whatsapp.send_text.return_value = {"messages": [{"id": "wamid-202"}]}

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["reminders_found"], 1)
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertEqual(summary["send_failures"], 0)

        candidate = summary["candidates"][0]
        self.assertEqual(candidate["transaction_id"], "tx-202")
        self.assertEqual(candidate["status"], "OVERDUE")
        self.assertEqual(candidate["days_overdue"], 3)
        self.assertIn("It is now 3 days overdue.", candidate["message"])

        self.mock_whatsapp.send_text.assert_called_once()
        _, kwargs = self.mock_whatsapp.send_text.call_args
        self.assertEqual(kwargs["to"], "+919876543211")
        self.assertIn("It is now 3 days overdue.", kwargs["text"])

    def test_future_due_credit_is_not_sent(self):
        """3. Future-due CREDIT transaction is not sent."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-3", "name": "Amit Patel", "phone": "+919876543212"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [
            {
                "transactionId": "tx-303",
                "customerId": "cust-3",
                "type": "CREDIT",
                "amount": 750,
                "dueDate": "2026-09-25",  # Future relative to 2026-09-20
            }
        ]

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["transactions_checked"], 1)
        self.assertEqual(summary["reminders_found"], 0)
        self.assertEqual(summary["reminders_sent"], 0)
        self.mock_whatsapp.send_text.assert_not_called()

    def test_payment_transaction_is_not_sent(self):
        """4. PAYMENT transaction is not sent."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-4", "name": "Deepak Kumar", "phone": "+919876543213"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [
            {
                "transactionId": "tx-404",
                "customerId": "cust-4",
                "type": "PAYMENT",
                "amount": 500,
                "dueDate": "2026-09-20",
            }
        ]

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["transactions_checked"], 1)
        self.assertEqual(summary["reminders_found"], 0)
        self.assertEqual(summary["reminders_sent"], 0)
        self.mock_whatsapp.send_text.assert_not_called()

    def test_customer_name_supplied_from_customer_record_to_reminder_service(self):
        """5. Customer name from the customer record is supplied to ReminderService without mutating DB."""
        # Note: LedgerService transaction records do NOT have customerName stored in DynamoDB
        raw_db_tx = {
            "transactionId": "tx-505",
            "customerId": "cust-5",
            "type": "CREDIT",
            "amount": 350,
            "dueDate": "2026-09-20",
        }
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-5", "name": "Sunita Devi", "phone": "+919876543214"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [raw_db_tx]

        # Spy on evaluate_transaction
        spy_evaluate = MagicMock(wraps=self.reminder_service.evaluate_transaction)
        runner_with_spy = ReminderRunner(
            ledger_service=self.mock_ledger,
            reminder_service=MagicMock(evaluate_transaction=spy_evaluate),
            whatsapp_service=self.mock_whatsapp,
        )

        summary = runner_with_spy.run(shop_id="shop-1", today=self.today)

        # 1. Verify evaluate_transaction received adapted transaction with customerName
        spy_evaluate.assert_called_once()
        passed_tx, _ = spy_evaluate.call_args[0], spy_evaluate.call_args[1]
        self.assertEqual(passed_tx[0]["customerName"], "Sunita Devi")

        # 2. Verify raw_db_tx was NOT mutated
        self.assertNotIn("customerName", raw_db_tx)

        # 3. Reminder was generated with the customer name
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertEqual(summary["candidates"][0]["customer_name"], "Sunita Devi")
        self.assertIn("Hi Sunita Devi,", summary["candidates"][0]["message"])

    def test_customer_phone_is_used_as_whatsapp_recipient(self):
        """6. Customer phone is used as the WhatsApp recipient."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-6", "name": "Vikram Singh", "phone": "+919123456789"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [
            {
                "transactionId": "tx-606",
                "customerId": "cust-6",
                "type": "CREDIT",
                "amount": 1000,
                "dueDate": "2026-09-20",
            }
        ]

        self.runner.run(shop_id="shop-test", today=self.today)

        self.mock_whatsapp.send_text.assert_called_once()
        _, kwargs = self.mock_whatsapp.send_text.call_args
        self.assertEqual(kwargs["to"], "+919123456789")

    def test_one_whatsapp_failure_does_not_stop_other_customers(self):
        """7. One WhatsApp failure does not stop other customers."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-fail", "name": "Failing Customer", "phone": "+919000000001"},
            {"customerId": "cust-ok", "name": "Successful Customer", "phone": "+919000000002"},
        ]
        self.mock_ledger.get_customer_transactions.side_effect = [
            [
                {
                    "transactionId": "tx-fail",
                    "customerId": "cust-fail",
                    "type": "CREDIT",
                    "amount": 500,
                    "dueDate": "2026-09-20",
                }
            ],
            [
                {
                    "transactionId": "tx-ok",
                    "customerId": "cust-ok",
                    "type": "CREDIT",
                    "amount": 800,
                    "dueDate": "2026-09-20",
                }
            ],
        ]

        # First customer send fails with an exception; second customer send succeeds
        self.mock_whatsapp.send_text.side_effect = [
            WhatsAppUnavailableError("Graph API unreachable"),
            {"messages": [{"id": "wamid-ok"}]},
        ]

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        # Both customers processed and both reminders identified
        self.assertEqual(summary["customers_processed"], 2)
        self.assertEqual(summary["reminders_found"], 2)
        # 1 sent, 1 failure
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertEqual(summary["send_failures"], 1)

        # Failure recorded in errors and details
        self.assertEqual(len(summary["errors"]), 1)
        self.assertEqual(summary["errors"][0]["customer_id"], "cust-fail")
        self.assertIn("Graph API unreachable", summary["errors"][0]["error"])

        self.assertEqual(len(summary["details"]), 2)
        self.assertFalse(summary["details"][0]["sent"])
        self.assertTrue(summary["details"][1]["sent"])

    def test_empty_customer_list_produces_clean_zero_count_result(self):
        """8. Empty customer list produces a clean zero-count result."""
        self.mock_ledger.list_customers.return_value = []

        summary = self.runner.run(shop_id="shop-empty", today=self.today)

        self.assertEqual(summary["shop_id"], "shop-empty")
        self.assertEqual(summary["customers_processed"], 0)
        self.assertEqual(summary["transactions_checked"], 0)
        self.assertEqual(summary["reminders_found"], 0)
        self.assertEqual(summary["reminders_sent"], 0)
        self.assertEqual(summary["send_failures"], 0)
        self.assertEqual(summary["candidates"], [])
        self.assertEqual(summary["details"], [])
        self.assertEqual(summary["errors"], [])
        self.mock_whatsapp.send_text.assert_not_called()

    def test_customer_with_no_transactions_is_handled_correctly(self):
        """9. Customer with no transactions is handled correctly."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-no-tx", "name": "New Customer", "phone": "+919876543299"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = []

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["customers_processed"], 1)
        self.assertEqual(summary["transactions_checked"], 0)
        self.assertEqual(summary["reminders_found"], 0)
        self.assertEqual(summary["reminders_sent"], 0)
        self.assertEqual(summary["send_failures"], 0)
        self.mock_whatsapp.send_text.assert_not_called()

    def test_customer_missing_phone_number_records_send_failure(self):
        """10. Customer with due transaction but missing phone number records send failure and does not abort."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-no-phone", "name": "No Phone User", "phone": ""},
            {"customerId": "cust-has-phone", "name": "Has Phone User", "phone": "+919988776655"},
        ]
        self.mock_ledger.get_customer_transactions.side_effect = [
            [
                {
                    "transactionId": "tx-np",
                    "customerId": "cust-no-phone",
                    "type": "CREDIT",
                    "amount": 200,
                    "dueDate": "2026-09-20",
                }
            ],
            [
                {
                    "transactionId": "tx-hp",
                    "customerId": "cust-has-phone",
                    "type": "CREDIT",
                    "amount": 400,
                    "dueDate": "2026-09-20",
                }
            ],
        ]
        self.mock_whatsapp.send_text.return_value = {"messages": [{"id": "wamid-hp"}]}

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["customers_processed"], 2)
        self.assertEqual(summary["reminders_found"], 2)
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertEqual(summary["send_failures"], 1)

        # Verify only customer with phone was sent WhatsApp message
        self.mock_whatsapp.send_text.assert_called_once()
        _, kwargs = self.mock_whatsapp.send_text.call_args
        self.assertEqual(kwargs["to"], "+919988776655")

    def test_transaction_fetch_error_does_not_abort_run(self):
        """11. Exception when fetching customer transactions does not stop other customers."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-db-err", "name": "DB Error Cust", "phone": "+919876543001"},
            {"customerId": "cust-valid", "name": "Valid Cust", "phone": "+919876543002"},
        ]
        self.mock_ledger.get_customer_transactions.side_effect = [
            Exception("DynamoDB connection timeout"),
            [
                {
                    "transactionId": "tx-valid",
                    "customerId": "cust-valid",
                    "type": "CREDIT",
                    "amount": 600,
                    "dueDate": "2026-09-20",
                }
            ],
        ]
        self.mock_whatsapp.send_text.return_value = {"messages": [{"id": "wamid-valid"}]}

        summary = self.runner.run(shop_id="shop-1", today=self.today)

        self.assertEqual(summary["customers_processed"], 2)
        self.assertEqual(summary["reminders_found"], 1)
        self.assertEqual(summary["reminders_sent"], 1)
        self.assertEqual(len(summary["errors"]), 1)
        self.assertEqual(summary["errors"][0]["customer_id"], "cust-db-err")
        self.assertIn("DynamoDB connection timeout", summary["errors"][0]["error"])

    def test_validation_invalid_shop_id(self):
        """12. Invalid shop_id raises ValueError."""
        with self.assertRaises(ValueError):
            self.runner.run(shop_id="", today=self.today)

        with self.assertRaises(ValueError):
            self.runner.run(shop_id="   ", today=self.today)

        with self.assertRaises(ValueError):
            self.runner.run(shop_id=None, today=self.today)

    def test_validation_invalid_today_date(self):
        """13. Invalid or missing today raises ValueError."""
        with self.assertRaises(ValueError):
            self.runner.run(shop_id="shop-1", today=None)

        with self.assertRaises(ValueError):
            self.runner.run(shop_id="shop-1", today="not-a-date")

    def test_injected_today_as_string_and_datetime(self):
        """14. String and datetime formats for 'today' are supported."""
        self.mock_ledger.list_customers.return_value = [
            {"customerId": "cust-dt", "name": "Date Test", "phone": "+919876543210"}
        ]
        self.mock_ledger.get_customer_transactions.return_value = [
            {
                "transactionId": "tx-dt",
                "customerId": "cust-dt",
                "type": "CREDIT",
                "amount": 250,
                "dueDate": "2026-09-20",
            }
        ]
        self.mock_whatsapp.send_text.return_value = {"messages": [{"id": "wamid-dt"}]}

        # ISO string
        summary_str = self.runner.run(shop_id="shop-1", today="2026-09-20")
        self.assertEqual(summary_str["reminders_sent"], 1)

        # Datetime object
        summary_dt = self.runner.run(shop_id="shop-1", today=datetime(2026, 9, 20, 14, 30))
        self.assertEqual(summary_dt["reminders_sent"], 1)


if __name__ == "__main__":
    unittest.main()
