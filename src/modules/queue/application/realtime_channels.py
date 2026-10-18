"""Valkey Pub/Sub channel naming for queue domain events."""

from uuid import UUID


def channel_queue_patient(atendimento_id: UUID | str) -> str:
    """Return canonical Valkey Pub/Sub channel for patient queue updates."""
    return f"medisync:pubsub:queue:{atendimento_id}"
