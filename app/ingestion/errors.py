"""Typed ingestion errors so the API layer can map them to precise HTTP statuses."""
from __future__ import annotations


class IngestionError(Exception):
    """Base class for all ingestion failures."""


class UnsupportedFileTypeError(IngestionError):
    """File extension is not one of the supported document types."""


class EmptyDocumentError(IngestionError):
    """The file contained no extractable text."""


class CorruptDocumentError(IngestionError):
    """The file could not be parsed (corrupt, encrypted, or wrong format)."""


class FileTooLargeError(IngestionError):
    """Upload exceeds the configured maximum size."""


class DocumentNotFoundError(IngestionError):
    """No document with the given id exists."""
