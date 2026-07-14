"""Reusable parser contracts for DRF transfer imports."""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from io import BytesIO, StringIO
from typing import Any, cast

from rn_forge.commons.excel import ExcelAdapter
from rn_forge.django.drf.views.renderers import TransferColumn

__all__ = [
    "CsvImportParser",
    "ExcelImportParser",
    "ImportParser",
    "JsonImportParser",
]


class ImportParser(ABC):
    """Abstract parser for format-specific import sources."""

    @abstractmethod
    def parse(
        self,
        source: object,
        columns: Sequence[TransferColumn],
    ) -> Sequence[Mapping[str, object]]:
        """Parse *source* into rows keyed by transfer column headers."""


class JsonImportParser(ImportParser):
    """Parse JSON-compatible row mappings."""

    def parse(
        self,
        source: object,
        columns: Sequence[TransferColumn],
    ) -> Sequence[Mapping[str, object]]:
        del columns
        data = json.loads(source) if isinstance(source, str) else source
        if not isinstance(data, list):
            raise TypeError("JSON import source must be a list of objects")
        return [
            dict(cast(Mapping[str, object], row)) for row in cast(list[object], data)
        ]


class CsvImportParser(ImportParser):
    """Parse CSV import sources into row mappings."""

    def parse(
        self,
        source: object,
        columns: Sequence[TransferColumn],
    ) -> Sequence[Mapping[str, object]]:
        del columns
        content = self._read_text(source)
        reader = csv.DictReader(StringIO(content))
        return [dict(cast(Mapping[str, object], row)) for row in reader]

    def _read_text(self, source: object) -> str:
        if isinstance(source, bytes):
            return source.decode("utf-8")
        if isinstance(source, str):
            return source
        read = getattr(source, "read", None)
        if callable(read):
            content = read()
            return (
                content.decode("utf-8") if isinstance(content, bytes) else str(content)
            )
        raise TypeError("CSV import source must be text, bytes, or a readable file")


class ExcelImportParser(ImportParser):
    """Parse Excel import sources into row mappings from the first worksheet."""

    def parse(
        self,
        source: object,
        columns: Sequence[TransferColumn],
    ) -> Sequence[Mapping[str, object]]:
        del columns
        workbook = ExcelAdapter.load_dataframe(BytesIO(self._read_bytes(source)))
        first_sheet = next(iter(workbook.values()))
        records = cast(Any, first_sheet).to_dict(orient="records")
        return [
            dict(cast(Mapping[str, object], row)) for row in cast(list[object], records)
        ]

    def _read_bytes(self, source: object) -> bytes:
        if isinstance(source, bytes):
            return source
        read = getattr(source, "read", None)
        if callable(read):
            content = read()
            if isinstance(content, bytes):
                return content
        raise TypeError("Excel import source must be bytes or a readable binary file")
