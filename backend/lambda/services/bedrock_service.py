"""
Ledgerly - Amazon Bedrock Transaction Extraction Service
Converts shopkeeper natural-language notes into structured transaction records.

Financial Rule:
Amazon Bedrock is ONLY used for entity extraction.
Customer balance arithmetic (balance = total CREDIT - total PAYMENT)
is strictly computed deterministically by backend code, NEVER by the AI model.
"""

import os
import json
import re
from typing import Any, Dict, Optional, Union

try:
    import boto3
    from botocore.exceptions import (
        BotoCoreError,
        ClientError,
        NoCredentialsError,
        PartialCredentialsError,
        EndpointConnectionError,
    )
except ImportError:
    boto3 = None
    BotoCoreError = ClientError = NoCredentialsError = PartialCredentialsError = EndpointConnectionError = Exception


class BedrockError(Exception):
    """Base exception for Bedrock operations."""
    pass


class BedrockUnavailableError(BedrockError):
    """Raised when AWS Bedrock is unreachable, credentials are missing, or service is offline."""
    pass


class BedrockExtractionError(BedrockError):
    """Raised when model response cannot be parsed or validation of extracted fields fails."""
    pass


EXTRACTION_SYSTEM_PROMPT = """You are a precise financial entity extractor for an Indian kirana store ledger assistant.
Your task is to extract transaction details from the shopkeeper's voice/text note.

You MUST extract exactly these 4 fields:
1. "customerName": Name of the customer (string). Must not be empty.
2. "type": Must be either "CREDIT" or "PAYMENT".
   - "CREDIT": Goods/items taken on credit (udhar), borrowed, or to be paid later.
   - "PAYMENT": Money paid, cash/UPI settlement, or debt cleared.
3. "amount": Positive transaction amount in Rupees (number). Must be greater than 0.
4. "description": Items or goods note mentioned (e.g. "rice", "2 packets of oil").
   - If no items or goods are mentioned (e.g. for payments like "Rahul paid 300"), use empty string "".

CRITICAL RULES:
- NEVER calculate or guess customer balances.
- NEVER output a balance or remaining amount.
- Output ONLY valid JSON matching this schema:
{"customerName": "...", "type": "CREDIT|PAYMENT", "amount": 100, "description": "..."}
- Do NOT output markdown code blocks (no ```json). Output raw JSON only."""


class BedrockService:
    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.model_id = model_id or os.environ.get(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
        )
        self.region_name = region_name or os.environ.get("AWS_REGION", "us-east-1")
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client

        if boto3 is None:
            raise BedrockUnavailableError("boto3 library is not available in the current environment.")

        try:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self.region_name,
            )
            return self._client
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise BedrockUnavailableError(
                f"AWS credentials not configured for Amazon Bedrock: {str(e)}"
            )
        except Exception as e:
            raise BedrockUnavailableError(
                f"Failed to initialize Amazon Bedrock client: {str(e)}"
            )

    def _build_model_payload(self, text: str) -> Dict[str, Any]:
        """Formats model payload based on provider API conventions."""
        model_lower = self.model_id.lower()

        if "anthropic" in model_lower:
            # Anthropic Claude Messages API
            return {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "temperature": 0.0,
                "system": EXTRACTION_SYSTEM_PROMPT,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Extract transaction information from this shopkeeper message:\n\"{text}\"",
                    }
                ],
            }
        elif "titan" in model_lower:
            # Amazon Titan
            prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\nShopkeeper message: \"{text}\"\n\nJSON output:"
            return {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 512,
                    "temperature": 0.0,
                    "stopSequences": ["\n\n"],
                },
            }
        else:
            # Generic fallback (e.g. Meta Llama, Amazon Nova)
            return {
                "prompt": f"{EXTRACTION_SYSTEM_PROMPT}\n\nInput: \"{text}\"\nJSON:",
                "max_gen_len": 512,
                "temperature": 0.0,
            }

    def _extract_text_from_response(self, response_body: Dict[str, Any]) -> str:
        """Extracts generated text string from model provider response structure."""
        model_lower = self.model_id.lower()

        if "anthropic" in model_lower:
            # Anthropic Claude format: {"content": [{"text": "...", "type": "text"}]}
            contents = response_body.get("content", [])
            for c in contents:
                if isinstance(c, dict) and c.get("type") == "text":
                    return c.get("text", "").strip()
            return ""

        if "titan" in model_lower:
            results = response_body.get("results", [])
            if results and isinstance(results[0], dict):
                return results[0].get("outputText", "").strip()
            return ""

        # Generic fallback checks
        if "generation" in response_body:
            return str(response_body["generation"]).strip()

        if "output" in response_body:
            return str(response_body["output"]).strip()

        return ""

    def parse_and_validate_extraction(self, raw_output: str) -> Dict[str, Any]:
        """
        Parses model text output into JSON and strictly validates:
        - customerName: non-empty string
        - type: CREDIT or PAYMENT
        - amount: positive numeric value
        - description: string (empty string if not specified)
        """
        if not raw_output or not raw_output.strip():
            raise BedrockExtractionError("Model returned an empty response.")

        cleaned = raw_output.strip()

        # Remove markdown code block fences if generated by model
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        # Locate JSON object boundaries
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            json_str = match.group(0)
        else:
            json_str = cleaned

        try:
            parsed = json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as e:
            raise BedrockExtractionError(f"Model output is not valid JSON: {raw_output}. Parse error: {str(e)}")

        if not isinstance(parsed, dict):
            raise BedrockExtractionError("Extracted data must be a JSON object dictionary.")

        # 1. Validate customerName
        if "customerName" not in parsed:
            raise BedrockExtractionError("Extracted transaction missing 'customerName'.")

        customer_name = str(parsed.get("customerName") or "").strip()
        if not customer_name:
            raise BedrockExtractionError("'customerName' cannot be empty.")

        # 2. Validate transaction type
        if "type" not in parsed:
            raise BedrockExtractionError("Extracted transaction missing 'type'.")

        tx_type = str(parsed.get("type") or "").strip().upper()
        if tx_type not in ("CREDIT", "PAYMENT"):
            raise BedrockExtractionError(
                f"Unsupported transaction type '{tx_type}'. Must be CREDIT or PAYMENT."
            )

        # 3. Validate amount
        if "amount" not in parsed:
            raise BedrockExtractionError("Extracted transaction missing 'amount'.")

        raw_amount = parsed.get("amount")
        try:
            amount = float(raw_amount)
        except (ValueError, TypeError):
            raise BedrockExtractionError(f"Amount must be a numeric value, received: {raw_amount}")

        if amount <= 0:
            raise BedrockExtractionError(f"Amount must be greater than zero, received: {amount}")

        # Format integer amounts cleanly (e.g. 500 instead of 500.0)
        formatted_amount: Union[int, float] = int(amount) if amount.is_integer() else amount

        # 4. Description
        description = str(parsed.get("description") or "").strip()

        return {
            "customerName": customer_name,
            "type": tx_type,
            "amount": formatted_amount,
            "description": description,
        }

    def extract_transaction(self, text: str) -> Dict[str, Any]:
        """
        Main entrypoint: sends natural language note to Bedrock and returns structured transaction.
        """
        if not text or not text.strip():
            raise BedrockExtractionError("Input text cannot be empty.")

        client = self._get_client()
        payload = self._build_model_payload(text.strip())

        try:
            response = client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload),
                contentType="application/json",
                accept="application/json",
            )
            raw_body = response.get("body")
            if hasattr(raw_body, "read"):
                response_data = json.loads(raw_body.read().decode("utf-8"))
            elif isinstance(raw_body, (str, bytes)):
                response_data = json.loads(raw_body)
            elif isinstance(raw_body, dict):
                response_data = raw_body
            else:
                response_data = {}
        except (NoCredentialsError, PartialCredentialsError) as e:
            raise BedrockUnavailableError(f"AWS credentials not configured for Amazon Bedrock: {str(e)}")
        except EndpointConnectionError as e:
            raise BedrockUnavailableError(f"Could not connect to Amazon Bedrock endpoint: {str(e)}")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "Unknown")
            msg = e.response.get("Error", {}).get("Message", str(e))
            raise BedrockUnavailableError(f"Bedrock ClientError [{code}]: {msg}")
        except BotoCoreError as e:
            raise BedrockUnavailableError(f"Bedrock BotoCoreError: {str(e)}")
        except Exception as e:
            raise BedrockUnavailableError(f"Failed during Bedrock invocation: {str(e)}")

        model_text = self._extract_text_from_response(response_data)
        return self.parse_and_validate_extraction(model_text)
