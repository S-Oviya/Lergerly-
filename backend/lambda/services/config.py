"""
Ledgerly - Configuration & Environment Validator
Modular validation for feature-specific environment settings.
Ensures clear, diagnostic error messages without breaking offline tests or unconfigured optional features.
"""

import os
from typing import Any, Dict, List, Optional, Sequence, Set


class ConfigValidationError(Exception):
    """Raised when required configuration variables for a requested feature are missing or invalid."""
    pass


def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieves stripped environment variable value or default."""
    val = os.environ.get(key)
    if val is not None and str(val).strip():
        return str(val).strip()
    return default


def validate_whatsapp_config(
    require_send: bool = False,
    require_verify: bool = False,
    require_secret: bool = False,
) -> Dict[str, str]:
    """
    Validates WhatsApp Meta Graph API settings based on requested capabilities.

    Args:
        require_send: If True, requires WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID.
        require_verify: If True, requires WHATSAPP_VERIFY_TOKEN for webhook GET validation.
        require_secret: If True, requires WHATSAPP_APP_SECRET for HMAC verification.

    Returns:
        Dict mapping validated keys to their string values.

    Raises:
        ConfigValidationError if any required variable is missing.
    """
    missing: List[str] = []
    config: Dict[str, str] = {}

    if require_verify:
        token = get_env_var("WHATSAPP_VERIFY_TOKEN")
        if not token:
            missing.append("WHATSAPP_VERIFY_TOKEN")
        else:
            config["WHATSAPP_VERIFY_TOKEN"] = token

    if require_send:
        token = get_env_var("WHATSAPP_TOKEN")
        if not token:
            missing.append("WHATSAPP_TOKEN")
        else:
            config["WHATSAPP_TOKEN"] = token

        pnid = get_env_var("WHATSAPP_PHONE_NUMBER_ID")
        if not pnid:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
        else:
            config["WHATSAPP_PHONE_NUMBER_ID"] = pnid

    if require_secret:
        secret = get_env_var("WHATSAPP_APP_SECRET")
        if not secret:
            missing.append("WHATSAPP_APP_SECRET")
        else:
            config["WHATSAPP_APP_SECRET"] = secret

    if missing:
        raise ConfigValidationError(
            f"Missing required WhatsApp configuration: {', '.join(missing)}. "
            "Please check your environment or .env file."
        )

    return config


def validate_dynamodb_config() -> Dict[str, str]:
    """
    Validates DynamoDB table configuration.
    Defaults CUSTOMERS_TABLE to 'Customers' and TRANSACTIONS_TABLE to 'Transactions'
    if not explicitly overridden.
    """
    customers_table = get_env_var("CUSTOMERS_TABLE", "Customers")
    transactions_table = get_env_var("TRANSACTIONS_TABLE", "Transactions")
    region = get_env_var("AWS_REGION", "us-east-1")

    return {
        "CUSTOMERS_TABLE": customers_table,
        "TRANSACTIONS_TABLE": transactions_table,
        "AWS_REGION": region,
    }


def validate_transcribe_config(require_bucket: bool = True) -> Dict[str, str]:
    """
    Validates AWS Transcribe audio configuration.

    Args:
        require_bucket: If True, requires TRANSCRIBE_S3_BUCKET for voice audio upload.
    """
    config: Dict[str, str] = {
        "AWS_REGION": get_env_var("AWS_REGION", "us-east-1"),
        "TRANSCRIBE_LANGUAGE": get_env_var("TRANSCRIBE_LANGUAGE", "auto"),
    }

    if require_bucket:
        bucket = get_env_var("TRANSCRIBE_S3_BUCKET")
        if not bucket:
            raise ConfigValidationError(
                "Missing required voice transcription configuration: TRANSCRIBE_S3_BUCKET is not set. "
                "AWS Transcribe requires an S3 bucket to process audio files."
            )
        config["TRANSCRIBE_S3_BUCKET"] = bucket

    return config


def validate_bedrock_config(require_model_id: bool = True) -> Dict[str, str]:
    """
    Validates Amazon Bedrock model configuration.
    """
    config: Dict[str, str] = {
        "AWS_REGION": get_env_var("AWS_REGION", "us-east-1"),
    }

    if require_model_id:
        model_id = get_env_var("BEDROCK_MODEL_ID")
        if not model_id:
            raise ConfigValidationError(
                "Missing required Amazon Bedrock configuration: BEDROCK_MODEL_ID is not set. "
                "Specify a foundation model ID (e.g. 'anthropic.claude-3-haiku-20240307-v1:0')."
            )
        config["BEDROCK_MODEL_ID"] = model_id

    return config


def validate_environment(
    features: Optional[Sequence[str]] = None,
) -> Dict[str, Dict[str, str]]:
    """
    Selectively validates environment configuration for the specified feature set.
    Supported feature names: 'whatsapp_verify', 'whatsapp_send', 'dynamodb', 'transcribe', 'bedrock'.

    If features is None, validates all basic active services without breaking on optional items.
    """
    if features is None:
        target_features = {"dynamodb"}
    else:
        target_features = {f.lower().strip() for f in features}

    results: Dict[str, Dict[str, str]] = {}
    errors: List[str] = []

    if "whatsapp_verify" in target_features:
        try:
            results["whatsapp_verify"] = validate_whatsapp_config(require_verify=True)
        except ConfigValidationError as e:
            errors.append(str(e))

    if "whatsapp_send" in target_features:
        try:
            results["whatsapp_send"] = validate_whatsapp_config(require_send=True)
        except ConfigValidationError as e:
            errors.append(str(e))

    if "dynamodb" in target_features:
        try:
            results["dynamodb"] = validate_dynamodb_config()
        except ConfigValidationError as e:
            errors.append(str(e))

    if "transcribe" in target_features:
        try:
            results["transcribe"] = validate_transcribe_config(require_bucket=True)
        except ConfigValidationError as e:
            errors.append(str(e))

    if "bedrock" in target_features:
        try:
            results["bedrock"] = validate_bedrock_config(require_model_id=True)
        except ConfigValidationError as e:
            errors.append(str(e))

    if errors:
        raise ConfigValidationError("\n".join(errors))

    return results
