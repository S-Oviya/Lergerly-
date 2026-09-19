"""
Unit tests for Reminder Templates (WhatsApp + Automation).
Verifies customer-facing reminder text generation and input validations.
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

from services.reminder_templates import (
    ReminderValidationError,
    render_due_reminder,
    render_overdue_reminder,
    validate_and_format_date,
)


class TestReminderTemplates(unittest.TestCase):
    """Unit tests for WhatsApp payment reminder templates."""

    def test_valid_due_reminder(self):
        """1. Test valid due-today payment reminder."""
        msg = render_due_reminder(
            customer_name="Rahul",
            amount=500,
            due_date="2026-09-20",
        )
        expected = (
            "Ledgerly\n"
            "\n"
            "Payment reminder\n"
            "\n"
            "Hi Rahul,\n"
            "\n"
            "Your payment of ₹500 is due today.\n"
            "\n"
            "Due date: 20 Sep 2026\n"
            "\n"
            "Please make the payment when convenient."
        )
        self.assertEqual(msg, expected)

    def test_valid_overdue_reminder(self):
        """2. Test valid overdue payment reminder."""
        msg = render_overdue_reminder(
            customer_name="Rahul",
            amount=500,
            due_date="2026-09-20",
            days_overdue=3,
        )
        expected = (
            "Ledgerly\n"
            "\n"
            "Payment reminder\n"
            "\n"
            "Hi Rahul,\n"
            "\n"
            "A payment of ₹500 was due on 20 Sep 2026.\n"
            "\n"
            "It is now 3 days overdue.\n"
            "\n"
            "Please make the payment when convenient."
        )
        self.assertEqual(msg, expected)

    def test_overdue_reminder_singular_day(self):
        """Test overdue reminder uses singular '1 day overdue' for 1 day."""
        msg = render_overdue_reminder(
            customer_name="Suresh",
            amount=250,
            due_date="2026-09-20",
            days_overdue=1,
        )
        self.assertIn("It is now 1 day overdue.", msg)

    def test_correct_inr_formatting(self):
        """3. Test INR formatting across various numeric and string amounts."""
        msg_int = render_due_reminder("Anita", 1000, "2026-09-20")
        self.assertIn("₹1,000", msg_int)

        msg_dec = render_due_reminder("Anita", 1250.50, "2026-09-20")
        self.assertIn("₹1,250.50", msg_dec)

        msg_decimal_obj = render_due_reminder("Anita", Decimal("750"), "2026-09-20")
        self.assertIn("₹750", msg_decimal_obj)

        msg_str = render_due_reminder("Anita", "300", "2026-09-20")
        self.assertIn("₹300", msg_str)

    def test_empty_customer_name_rejected(self):
        """4. Test empty or whitespace-only customer name raises ReminderValidationError."""
        with self.assertRaises(ReminderValidationError):
            render_due_reminder("", 500, "2026-09-20")

        with self.assertRaises(ReminderValidationError):
            render_due_reminder("   ", 500, "2026-09-20")

        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("", 500, "2026-09-20", 2)

    def test_zero_amount_rejected(self):
        """5. Test zero amount raises ReminderValidationError."""
        with self.assertRaises(ReminderValidationError):
            render_due_reminder("Rahul", 0, "2026-09-20")

        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", 0, "2026-09-20", 3)

    def test_negative_amount_rejected(self):
        """6. Test negative amount raises ReminderValidationError."""
        with self.assertRaises(ReminderValidationError):
            render_due_reminder("Rahul", -500, "2026-09-20")

        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", -100.50, "2026-09-20", 2)

        with self.assertRaises(ReminderValidationError):
            render_due_reminder("Rahul", "-250", "2026-09-20")

    def test_invalid_date_rejected(self):
        """7. Test invalid, empty, or unparseable date raises ReminderValidationError."""
        with self.assertRaises(ReminderValidationError):
            validate_and_format_date("not-a-valid-date")

        with self.assertRaises(ReminderValidationError):
            validate_and_format_date("")

        with self.assertRaises(ReminderValidationError):
            validate_and_format_date(None)

        with self.assertRaises(ReminderValidationError):
            render_due_reminder("Rahul", 500, "invalid-date-string")

    def test_valid_date_objects_accepted(self):
        """Test datetime.date objects format cleanly."""
        formatted = validate_and_format_date(date(2026, 9, 20))
        self.assertEqual(formatted, "20 Sep 2026")

    def test_invalid_days_overdue_rejected(self):
        """8. Test zero, negative, non-numeric, or invalid days_overdue raise ReminderValidationError."""
        # Zero days overdue
        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", 500, "2026-09-20", 0)

        # Negative days overdue
        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", 500, "2026-09-20", -3)

        # Non-integer float
        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", 500, "2026-09-20", 2.5)

        # None or string
        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", 500, "2026-09-20", None)

        with self.assertRaises(ReminderValidationError):
            render_overdue_reminder("Rahul", 500, "2026-09-20", "three")


if __name__ == "__main__":
    unittest.main()
