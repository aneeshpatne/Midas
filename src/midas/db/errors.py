"""Domain errors for Midas DB."""

from __future__ import annotations


class MidasDbError(Exception):
    """Base error for Midas DB operations."""


class NotFoundError(MidasDbError):
    def __init__(self, entity: str, id_: str) -> None:
        super().__init__(f"{entity} not found: {id_}")
        self.entity = entity
        self.id = id_


class ValidationError(MidasDbError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
