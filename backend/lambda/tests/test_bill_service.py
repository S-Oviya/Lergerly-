"""
Unit tests for BillService (Automation / WhatsApp).
Verifies structured transaction -> WhatsApp bill message generation.
"""

import os
import sys
import unittest

# Ensure backend/lambda is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
lambda_dir = os.path.abspath(os.path.join(current_dir, ".."))
if lambda_dir not in sys.path:
    sys.path.insert(0, lambda_dir)

from services.bill_service import BillService
from services.message_templates import TemplateValidationError


class TestBillService(unittest.TestCase):
    """Tests for BillService structured transaction processing and bill generation."""

    def setUp(self):
        self.service = BillService()

    def test_generate_bill_credit_camel_case(self):
        """Test bill generation with standard API/frontend camelCase dictionary."""
        tx_data = {
            "customerName": "Rahul",
            "type": "CREDIT",
            "amount": 500,
            "description": "Rice",
            "dueDate": "20 Sep 2026",
        }
        bill_text = self.service.generate_bill(tx_data)
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
        self.assertEqual(bill_text, expected)

    def test_generate_bill_snake_case_fields(self):
        """Test bill generation with backend snake_case dictionary."""
        tx_data = {
            "customer_name": "Suresh Kumar",
            "transaction_type": "CREDIT",
            "amount": 750,
            "items_note": "Sugar 5kg",
            "due_date": "25 Sep 2026",
        }
        bill_text = self.service.generate_bill(tx_data)
        self.assertIn("Customer: Suresh Kumar", bill_text)
        self.assertIn("Item: Sugar 5kg", bill_text)
        self.assertIn("Amount: ₹750", bill_text)
        self.assertIn("Status: Credit", bill_text)
        self.assertIn("Due date: 25 Sep 2026", bill_text)

    def test_generate_bill_payment(self):
        """Test bill generation for a PAYMENT transaction."""
        tx_data = {
            "customerName": "Rahul",
            "type": "PAYMENT",
            "amount": 300,
        }
        bill_text = self.service.generate_bill(tx_data)
        self.assertIn("Customer: Rahul", bill_text)
        self.assertIn("Amount: ₹300", bill_text)
        self.assertIn("Status: Payment", bill_text)
        self.assertNotIn("Item:", bill_text)
        self.assertNotIn("Due date:", bill_text)

    def test_generate_bill_missing_optional_due_date(self):
        """Test bill generation when due date is omitted."""
        tx_data = {
            "customerName": "Anita",
            "type": "CREDIT",
            "amount": 400,
            "description": "Milk & Bread",
        }
        bill_text = self.service.generate_bill(tx_data)
        self.assertIn("Customer: Anita", bill_text)
        self.assertIn("Item: Milk & Bread", bill_text)
        self.assertIn("Amount: ₹400", bill_text)
        self.assertIn("Status: Credit", bill_text)
        self.assertNotIn("Due date:", bill_text)

    def test_generate_bill_special_characters(self):
        """Test bill generation preserving special characters and kirana store notes."""
        tx_data = {
            "customerName": "K.V. & Sons / Kirana",
            "type": "CREDIT",
            "amount": 1499.50,
            "description": "Oil 2L @ ₹160/L + Rice 10kg (Basmati)",
            "dueDate": "15-10-2026",
        }
        bill_text = self.service.generate_bill(tx_data)
        self.assertIn("Customer: K.V. & Sons / Kirana", bill_text)
        self.assertIn("Item: Oil 2L @ ₹160/L + Rice 10kg (Basmati)", bill_text)
        self.assertIn("Amount: ₹1,499.50", bill_text)
        self.assertIn("Due date: 15-10-2026", bill_text)

    def test_generate_payment_receipt_dict_and_args(self):
        """Test payment receipt generation via dictionary and positional arguments."""
        # Via dictionary
        receipt_dict = self.service.generate_payment_receipt({
            "customerName": "Rahul",
            "amount": 500,
            "referenceId": "REC-9988",
        })
        self.assertIn("Customer: Rahul", receipt_dict)
        self.assertIn("Amount paid: ₹500", receipt_dict)
        self.assertIn("Receipt ID: REC-9988", receipt_dict)

        # Via positional arguments
        receipt_args = self.service.generate_payment_receipt("Rahul", 500)
        self.assertIn("Customer: Rahul", receipt_args)
        self.assertIn("Amount paid: ₹500", receipt_args)
        self.assertNotIn("Receipt ID:", receipt_args)

    def test_format_bill_details_direct(self):
        """Test direct formatting helper format_bill_details."""
        bill_text = self.service.format_bill_details(
            customer_name="Pooja",
            transaction_type="CREDIT",
            amount=650,
            description="Soaps & Detergents",
            due_date="01-11-2026",
        )
        self.assertIn("Customer: Pooja", bill_text)
        self.assertIn("Item: Soaps & Detergents", bill_text)
        self.assertIn("Amount: ₹650", bill_text)

    def test_validation_non_dict_transaction(self):
        """Test passing non-dict object raises TemplateValidationError."""
        with self.assertRaises(TemplateValidationError):
            self.service.generate_bill("invalid string")

    def test_validation_missing_fields(self):
        """Test missing required customer, type, or amount raises TemplateValidationError."""
        with self.assertRaises(TemplateValidationError):
            self.service.generate_bill({"type": "CREDIT", "amount": 500})

        with self.assertRaises(TemplateValidationError):
            self.service.generate_bill({"customerName": "Rahul", "amount": 500})

        with self.assertRaises(TemplateValidationError):
            self.service.generate_bill({"customerName": "Rahul", "type": "CREDIT"})

    def test_validation_invalid_type_and_amount(self):
        """Test invalid transaction type and non-positive amount."""
        with self.assertRaises(TemplateValidationError):
            self.service.generate_bill({
                "customerName": "Rahul",
                "type": "UNKNOWN",
                "amount": 500,
            })

        with self.assertRaises(TemplateValidationError):
            self.service.generate_bill({
                "customerName": "Rahul",
                "type": "CREDIT",
                "amount": -50,
            })


if __name__ == "__main__":
    unittest.main()
