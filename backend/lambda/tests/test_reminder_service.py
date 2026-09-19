"""
Unit tests for ReminderService (WhatsApp + Automation).
Verifies reminder logic, deterministic date comparison, duplicate suppression,
and architectural boundaries (zero balance calculation).
"""

import os
import sys
import unittest
from datetime import date
from decimal import Decimal

# Ensure backend/lambda is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

from services.reminder_service import ReminderService
from services.reminder_templates import ReminderValidationError


class TestReminderService(unittest.TestCase):
    """Unit tests for ReminderService."""

    def setUp(self):
        self.service = ReminderService()

    def test_future_due_date_produces_no_reminder(self):
        """1. Future due date (due_date > today) produces no reminder."""
        tx = {
            "id": "txn-001",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2026-09-25",
        }
        today = date(2026, 9, 20)
        reminder = self.service.evaluate_transaction(tx, today=today)
        self.assertIsNone(reminder)

    def test_due_today_produces_due(self):
        """2. Due today (due_date == today) produces DUE status and due reminder message."""
        tx = {
            "id": "txn-002",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2026-09-20",
        }
        today = date(2026, 9, 20)
        reminder = self.service.evaluate_transaction(tx, today=today)

        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["transaction_id"], "txn-002")
        self.assertEqual(reminder["customer_name"], "Rahul")
        self.assertEqual(reminder["amount"], 500)
        self.assertEqual(reminder["status"], "DUE")
        self.assertNotIn("days_overdue", reminder)
        self.assertIn("Your payment of ₹500 is due today.", reminder["message"])

    def test_past_due_date_produces_overdue(self):
        """3. Past due date (due_date < today) produces OVERDUE status."""
        tx = {
            "id": "txn-003",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2026-09-17",
        }
        today = date(2026, 9, 20)
        reminder = self.service.evaluate_transaction(tx, today=today)

        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["status"], "OVERDUE")
        self.assertEqual(reminder["days_overdue"], 3)
        self.assertIn("It is now 3 days overdue.", reminder["message"])

    def test_correct_days_overdue_calculation(self):
        """4. Correct days-overdue calculation based purely on date difference."""
        tx = {
            "customerName": "Priya",
            "amount": 1200,
            "type": "CREDIT",
            "dueDate": "2026-09-10",
        }
        today = date(2026, 9, 25)
        reminder = self.service.evaluate_transaction(tx, today=today)

        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["days_overdue"], 15)
        self.assertIn("It is now 15 days overdue.", reminder["message"])

    def test_payment_records_are_ignored(self):
        """5. Payment records (type == 'PAYMENT') are ignored; no reminder is generated."""
        payment_tx = {
            "id": "txn-004",
            "customerName": "Rahul",
            "amount": 500,
            "type": "PAYMENT",
            "dueDate": "2026-09-20",
        }
        today = date(2026, 9, 20)
        self.assertIsNone(self.service.evaluate_transaction(payment_tx, today=today))

    def test_invalid_records_are_handled_cleanly(self):
        """6. Invalid or corrupt records are handled cleanly without raising unhandled exceptions."""
        today = date(2026, 9, 20)

        # Non-dictionary input
        self.assertIsNone(self.service.evaluate_transaction("invalid", today=today))

        # Empty dictionary
        self.assertIsNone(self.service.evaluate_transaction({}, today=today))

        # Missing customer name
        self.assertIsNone(self.service.evaluate_transaction({"amount": 500, "dueDate": "2026-09-20", "type": "CREDIT"}, today=today))

        # Missing or negative amount
        self.assertIsNone(self.service.evaluate_transaction({"customerName": "Rahul", "amount": -100, "dueDate": "2026-09-20", "type": "CREDIT"}, today=today))

        # Missing due date
        self.assertIsNone(self.service.evaluate_transaction({"customerName": "Rahul", "amount": 500, "type": "CREDIT"}, today=today))

        # Corrupt due date string
        self.assertIsNone(self.service.evaluate_transaction({"customerName": "Rahul", "amount": 500, "dueDate": "corrupt-date", "type": "CREDIT"}, today=today))

    def test_same_day_duplicate_reminder_is_suppressed(self):
        """7. Same-day duplicate reminder is suppressed if lastReminderDate == today."""
        tx = {
            "id": "txn-005",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2026-09-15",
            "lastReminderDate": "2026-09-20",
        }
        today = date(2026, 9, 20)
        reminder = self.service.evaluate_transaction(tx, today=today)
        self.assertIsNone(reminder)

    def test_reminder_generated_again_on_later_day(self):
        """8. Reminder can be generated again on a later day if the transaction is still overdue."""
        tx = {
            "id": "txn-006",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2026-09-15",
            "lastReminderDate": "2026-09-20",  # Reminded yesterday
        }
        today = date(2026, 9, 21)  # Next day
        reminder = self.service.evaluate_transaction(tx, today=today)

        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["status"], "OVERDUE")
        self.assertEqual(reminder["days_overdue"], 6)

    def test_multiple_independent_transactions_handled(self):
        """9. Multiple transactions (future, due today, overdue) are evaluated independently."""
        transactions = [
            {
                "id": "tx-A",
                "customerName": "Customer A",
                "amount": 100,
                "type": "CREDIT",
                "dueDate": "2026-09-25",  # Future -> Ignore
            },
            {
                "id": "tx-B",
                "customerName": "Customer B",
                "amount": 200,
                "type": "CREDIT",
                "dueDate": "2026-09-20",  # Due today -> DUE
            },
            {
                "id": "tx-C",
                "customerName": "Customer C",
                "amount": 300,
                "type": "CREDIT",
                "dueDate": "2026-09-18",  # Overdue -> OVERDUE
            },
        ]
        today = date(2026, 9, 20)
        reminders = self.service.process_transactions(transactions, today=today)

        self.assertEqual(len(reminders), 2)
        self.assertEqual(reminders[0]["transaction_id"], "tx-B")
        self.assertEqual(reminders[0]["status"], "DUE")
        self.assertEqual(reminders[1]["transaction_id"], "tx-C")
        self.assertEqual(reminders[1]["status"], "OVERDUE")

    def test_injected_today_is_used(self):
        """10. Injected 'today' date is strictly used instead of system date."""
        tx = {
            "id": "tx-fixed",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2028-01-01",
        }
        # In the far future relative to real world, but due on 2028-01-01
        today = date(2028, 1, 1)
        reminder = self.service.evaluate_transaction(tx, today=today)
        self.assertIsNotNone(reminder)
        self.assertEqual(reminder["status"], "DUE")

        # Requiring explicit today
        with self.assertRaises(ReminderValidationError):
            self.service.evaluate_transaction(tx, today=None)

    def test_amount_passed_through_unchanged(self):
        """11. Amount is passed through completely unchanged without financial rounding/modification."""
        amount_dec = Decimal("450.75")
        tx = {
            "id": "tx-amount",
            "customerName": "Rahul",
            "amount": amount_dec,
            "type": "CREDIT",
            "dueDate": "2026-09-20",
        }
        today = date(2026, 9, 20)
        reminder = self.service.evaluate_transaction(tx, today=today)
        self.assertEqual(reminder["amount"], amount_dec)

    def test_service_does_not_calculate_customer_balances(self):
        """
        12. Strict architectural boundary:
        Two separate unpaid transactions for the SAME customer ('Rahul')
        are NOT merged, added, or balance-calculated. Each produces an independent candidate.
        """
        tx1 = {
            "id": "tx-001",
            "customerName": "Rahul",
            "amount": 500,
            "type": "CREDIT",
            "dueDate": "2026-09-20",
        }
        tx2 = {
            "id": "tx-002",
            "customerName": "Rahul",
            "amount": 250,
            "type": "CREDIT",
            "dueDate": "2026-09-20",
        }

        today = date(2026, 9, 20)
        reminders = self.service.process_transactions([tx1, tx2], today=today)

        # Must produce TWO separate reminders, never combined to ₹750
        self.assertEqual(len(reminders), 2)
        self.assertEqual(reminders[0]["amount"], 500)
        self.assertEqual(reminders[1]["amount"], 250)
        self.assertNotEqual(reminders[0]["amount"], 750)


if __name__ == "__main__":
    unittest.main()
