from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


SCHEMA_DIR = Path(__file__).with_name("schema")
CONTRACT_FILES = {
    "state_object": "ak_state_object.schema.yaml",
    "state_event": "ak_state_event.schema.yaml",
    "placement_decision": "placement_decision.schema.yaml",
    "vllm_ascend_observation": "vllm_ascend_observation.schema.yaml",
}


class ValidationError(ValueError):
    """Raised when a state-runtime record violates its declared contract."""


@lru_cache(maxsize=1)
def load_contracts() -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for name, filename in CONTRACT_FILES.items():
        path = SCHEMA_DIR / filename
        with path.open(encoding="utf-8") as handle:
            contract = yaml.safe_load(handle)
        if not isinstance(contract, dict):
            raise ValidationError(f"{path} must contain a YAML mapping")
        if contract.get("record_name") != name:
            raise ValidationError(f"{path} record_name must be {name}")
        contracts[name] = contract
    return contracts


def validate_record(contract_name: str, record: Mapping[str, Any]) -> None:
    contracts = load_contracts()
    if contract_name not in contracts:
        raise ValidationError(f"unknown contract: {contract_name}")

    contract = contracts[contract_name]
    required_fields = set(contract.get("required_fields", []))
    missing = sorted(required_fields - set(record))
    if missing:
        raise ValidationError(f"missing required fields: {', '.join(missing)}")

    extra = sorted(set(record) - required_fields)
    if extra:
        raise ValidationError(f"unexpected fields: {', '.join(extra)}")

    expected_version = str(contract.get("schema_version"))
    if record.get("schema_version") != expected_version:
        raise ValidationError(
            f"schema_version must be {expected_version}, got {record.get('schema_version')!r}"
        )

    nullable = set(contract.get("nullable_fields", []))
    field_types = contract.get("field_types", {})
    enums = contract.get("enums", {})
    for field_name in required_fields:
        value = record[field_name]
        if value is None:
            if field_name not in nullable:
                raise ValidationError(f"{field_name} must not be null")
            continue
        _validate_type(field_name, value, field_types.get(field_name))
        allowed = enums.get(field_name)
        if allowed is not None and value not in allowed:
            raise ValidationError(
                f"{field_name} must be one of {allowed}, got {value!r}"
            )


def _validate_type(field_name: str, value: Any, expected: str | None) -> None:
    if expected is None:
        return
    predicates = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    if expected not in predicates:
        raise ValidationError(f"unsupported field type {expected!r} for {field_name}")
    if not predicates[expected](value):
        raise ValidationError(f"{field_name} must be {expected}, got {type(value).__name__}")
