"""Identity infrastructure adapters."""

from src.modules.identity.infrastructure.fake_sms_adapter import FakeSmsSenderAdapter
from src.modules.identity.infrastructure.identity_reader_sql import SqlIdentityReader

__all__ = [
    "FakeSmsSenderAdapter",
    "SqlIdentityReader",
]
