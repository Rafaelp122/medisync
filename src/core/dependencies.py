"""Centralized FastAPI infrastructure dependencies."""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from src.core.valkey import get_valkey_client

__all__ = ["ValkeyDep"]

ValkeyDep = Annotated[Redis, Depends(get_valkey_client)]
