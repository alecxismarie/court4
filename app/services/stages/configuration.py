from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_SECRET_KEY_PARTS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def effective_stage_configuration(
    base: Mapping[str, Any],
    request_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a normalized, secret-free deep merge of defaults and executed overrides."""
    merged = _deep_merge(dict(base), dict(request_overrides or {}))
    normalized = _normalize(merged)
    if not isinstance(normalized, dict):
        raise TypeError("Stage configuration must normalize to an object.")
    return normalized


def stage_configuration_fingerprint(configuration: Mapping[str, Any]) -> str:
    normalized = effective_stage_configuration(configuration)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in overrides.items():
        if _is_secret_key(key):
            continue
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(dict(existing), dict(value))
        else:
            result[key] = value
    return result


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if not _is_secret_key(str(key))
        }
    if isinstance(value, set | frozenset):
        normalized_items = [_normalize(item) for item in value]
        return sorted(normalized_items, key=_stable_sort_key)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_normalize(item) for item in value]
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime | date):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"Unsupported stage configuration value: {type(value).__name__}")


def _stable_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _SECRET_KEY_PARTS)
