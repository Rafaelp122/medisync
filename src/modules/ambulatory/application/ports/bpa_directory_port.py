"""Port for directory lookup of data for BPA-I export."""

from typing import Protocol, runtime_checkable

from src.modules.ambulatory.application.dtos import BpaRegistroDetalheDTO


@runtime_checkable
class BpaDirectoryPort(Protocol):
    """Abstract reader for org, physician, and patient details for BPA-I."""

    async def buscar_detalhes_bpa_lote(
        self,
        organizacao_id: int,
        competencia: str,
    ) -> list[BpaRegistroDetalheDTO]:
        """Fetch all individual production items with patient and doctor details."""
        ...
