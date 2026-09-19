"""
Unit tests for WhatsApp message templates (Automation / WhatsApp).
Uses Python standard unittest library without requiring external dependencies or credentials.
"""

import os
import sys
import unittest
from decimal import Decimal

# Ensure backend/lambda is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

from services.message_templates import (
    TemplateValidationError,
    format_inr,
    render_payment_confirmation,
    render_transaction_confirmation,
)


class TestMessageTemplates(unittest.TestCase):
    """Unit tests for WhatsApp pure template generation functions."""

    def test_credit_confirmation_with_all_fields(self):
        """Test CREDIT transaction confirmation with customer, item, amount, status, and due date."""
        msg = render_transaction_confirmation(
            customer_name="Rahul",
            transaction_type="CREDIT",
            amount=500,
            description="Rice",
            due_date="20 Sep 2026",
        )
        expected = (
            "Ledgerly\n"
            "Transaction recorded\n"
            "\n"
            "Customer: Rahul\n"
            "Item: Rice\n"
            "Amount: ₹500\n"
            "Status: Credit\n"
            "Due date: 20 Sep 2026"
        )
        self.assertEqual(msg, expected)

    def test_payment_confirmation_render(self):
        """Test dedicated payment confirmation template."""
        msg = render_payment_confirmation(
            customer_name="Rahul",
            amount=500,
        )
        expected = (
            "Ledgerly\n"
            "Payment recorded\n"
            "\n"
            "Customer: Rahul\n"
            "Amount paid: ₹500"
        )
        self.assertEqual(msg, expected)

    def test_transaction_confirmation_for_payment_type(self):
        """Test generic transaction confirmation when transaction_type is PAYMENT."""
        msg = render_transaction_confirmation(
            customer_name="Priya Sharma",
            transaction_type="PAYMENT",
            amount=1200,
            description="Partial settlement",
        )
        self.assertIn("Customer: Priya Sharma", msg)
        self.assertIn("Item: Partial settlement", msg)
        self.assertIn("Amount: ₹1,200", msg)
        self.assertIn("Status: Payment", msg)
        self.assertNotIn("Due date", msg)

    def test_due_date_included(self):
        """Test that due date appears formatted when provided."""
        msg = render_transaction_confirmation(
            customer_name="Anita",
            transaction_type="CREDIT",
            amount=350,
            description="Cooking Oil",
            due_date="05 Oct 2026",
        )
        self.assertIn("Due date: 05 Oct 2026", msg)

    def test_missing_optional_due_date(self):
        """Test that due date line is completely omitted when None or empty."""
        msg_none = render_transaction_confirmation(
            customer_name="Anita",
            transaction_type="CREDIT",
            amount=350,
            due_date=None,
        )
        self.assertNotIn("Due date", msg_none)

        msg_empty = render_transaction_confirmation(
            customer_name="Anita",
            transaction_type="CREDIT",
            amount=350,
            due_date="   ",
        )
        self.assertNotIn("Due date", msg_empty)

    def test_missing_optional_description(self):
        """Test that item line is omitted when description is missing or empty."""
        msg = render_transaction_confirmation(
            customer_name="Vikas",
            transaction_type="CREDIT",
            amount=200,
            description="",
        )
        self.assertNotIn("Item:", msg)
        self.assertIn("Customer: Vikas", msg)
        self.assertIn("Amount: ₹200", msg)

    def test_inr_amount_formatting(self):
        """Test INR formatting across integer, decimal, string, and Decimal inputs."""
        self.assertEqual(format_inr(500), "₹500")
        self.assertEqual(format_inr(500.0), "₹500")
        self.assertEqual(format_inr(1250.50), "₹1,250.50")
        self.assertEqual(format_inr(100000), "₹100,000")
        self.assertEqual(format_inr(Decimal("750.25")), "₹750.25")
        self.assertEqual(format_inr("450"), "₹450")
        self.assertEqual(format_inr("999.99"), "₹999.99")

    def test_special_characters_in_customer_and_description(self):
        """Test formatting preserves special characters, punctuation, and store symbols."""
        msg = render_transaction_confirmation(
            customer_name="M/s. Sharma & Sons (Kirana #1)",
            transaction_type="CREDIT",
            amount=850,
            description="Atta 10kg @ ₹45/kg + 2x Dahi (500g)",
            due_date="30-10-2026",
        )
        self.assertIn("Customer: M/s. Sharma & Sons (Kirana #1)", msg)
        self.assertIn("Item: Atta 10kg @ ₹45/kg + 2x Dahi (500g)", msg)
        self.assertIn("Amount: ₹850", msg)
        self.assertIn("Status: Credit", msg)
        self.assertIn("Due date: 30-10-2026", msg)

    def test_invalid_transaction_type(self):
        """Test that invalid or unsupported transaction types raise TemplateValidationError."""
        with self.assertRaises(TemplateValidationError):
            render_transaction_confirmation("Rahul", "DEBIT", 500)

        with self.assertRaises(TemplateValidationError):
            render_transaction_confirmation("Rahul", "TRANSFER", 500)

        with self.assertRaises(TemplateValidationError):
            render_transaction_confirmation("Rahul", "", 500)

    def test_invalid_and_non_positive_amount(self):
        """Test that zero, negative, or non-numeric amounts raise TemplateValidationError."""
        # Zero amount
        with self.assertRaises(TemplateValidationError):
            format_inr(0)

        # Negative amounts
        with self.assertRaises(TemplateValidationError):
            format_inr(-500)

        with self.assertRaises(TemplateValidationError):
            format_inr("-25.50")

        # Non-numeric inputs
        with self.assertRaises(TemplateValidationError):
            format_inr("abc")

        with self.assertRaises(TemplateValidationError):
            format_inr(None)

        with self.assertRaises(TemplateValidationError):
            render_transaction_confirmation("Rahul", "CREDIT", 0)

        with self.assertRaises(TemplateValidationError):
            render_payment_confirmation("Rahul", -100)

    def test_missing_or_empty_customer_name(self):
        """Test that empty or whitespace-only customer names raise TemplateValidationError."""
        with self.assertRaises(TemplateValidationError):
            render_transaction_confirmation("", "CREDIT", 500)

        with self.assertRaises(TemplateValidationError):
            render_transaction_confirmation("   ", "CREDIT", 500)

        with self.assertRaises(TemplateValidationError):
            render_payment_confirmation("", 500)


if __name__ == "__main__":
    unittest.main()
