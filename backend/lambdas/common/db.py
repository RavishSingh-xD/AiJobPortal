"""
Shared DynamoDB helpers for Lambdas.

Individual handlers still create their own table resources so each
Lambda zip stays self-contained. Use these helpers when extracting
shared logic or local scripts.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import boto3

_REGION = os.environ.get("AWS_REGION", "ap-south-1")
_dynamodb = None


def get_dynamodb():
    """Return a process-wide DynamoDB resource."""
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=_REGION)
    return _dynamodb


def get_table(table_name: str, env_var: Optional[str] = None):
    """
    Resolve a DynamoDB Table.

    Prefer an explicit table_name; if env_var is given and set, that wins.
    """
    resolved = (os.environ.get(env_var) if env_var else None) or table_name
    return get_dynamodb().Table(resolved)
