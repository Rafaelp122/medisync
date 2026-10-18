"""Valkey Pub/Sub channel naming for consultation domain events."""

from uuid import UUID


def channel_doctor_calls(medico_id: UUID | str) -> str:
    """Return canonical Valkey Pub/Sub channel for doctor incoming calls."""
    return f"medisync:pubsub:doctor:{medico_id}"
