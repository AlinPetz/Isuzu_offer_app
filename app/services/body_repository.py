from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from app.models.body_models import (
    CATEGORY_FIELDS,
    COMMON_FIELDS,
    ReviewedBody,
)


COMMON_HEADERS = [
    "body_id",
    *COMMON_FIELDS,
    "compatible_chassis_ids",
    "document_sursa",
    "warnings",
    "extraction_notes",
]

CATEGORY_SHEETS = {
    "Frigorifica": "Frigorifice",
    "Platforma": "Platforme_Bene",
    "Bena fixa": "Platforme_Bene",
    "Basculanta": "Basculante",
    "Hooklift": "Hooklift",
    "Macara": "Macarale",
}


class BodyRepositoryError(Exception):
    user_message = "Baza de date caroserii nu a putut fi actualizata."


class BodyWorkbookLockedError(BodyRepositoryError):
    user_message = "Fisierul Excel pentru caroserii pare deschis. Inchideti Excel si incercati din nou."


class BodyRepository:
    def __init__(self, workbook_path: Path):
        self.workbook_path = workbook_path

    def list_bodies(self) -> List[Dict[str, Any]]:
        if not self.workbook_path.exists():
            return []
        workbook = load_workbook(self.workbook_path)
        if "Caroserii" not in workbook.sheetnames:
            return []
        sheet = workbook["Caroserii"]
        headers = [cell.value for cell in sheet[1]]
        rows = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            rows.append(dict(zip(headers, row)))
        return rows

    def next_body_id(self) -> str:
        highest = 0
        for row in self.list_bodies():
            value = str(row.get("body_id") or "")
            match = re.match(r"BODY-(\d+)$", value)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"BODY-{highest + 1:04d}"

    def find_duplicate(self, body_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        keys = ("furnizor", "nr_oferta_furnizor", "data_oferta")
        target = {key: self._clean_compare(body_data.get(key)) for key in keys}
        if not all(target.values()):
            return None
        for row in self.list_bodies():
            if all(self._clean_compare(row.get(key)) == target[key] for key in keys):
                return row
        return None

    def save_body(self, body: ReviewedBody) -> str:
        workbook = self._load_or_create_workbook()
        self._ensure_template(workbook)
        body_id = body.body_id or self.next_body_id()
        body.body_id = body_id

        self._append_row(workbook["Caroserii"], COMMON_HEADERS, self._common_row(body))

        category_sheet = CATEGORY_SHEETS.get(body.categorie or "")
        if category_sheet:
            fields = ["body_id", *CATEGORY_FIELDS.get(body.categorie or "", [])]
            self._append_row(workbook[category_sheet], fields, self._category_row(body, fields))

        try:
            workbook.save(self.workbook_path)
        except PermissionError as error:
            raise BodyWorkbookLockedError() from error
        return body_id

    def _load_or_create_workbook(self):
        self.workbook_path.parent.mkdir(parents=True, exist_ok=True)
        if self.workbook_path.exists():
            return load_workbook(self.workbook_path)
        workbook = Workbook()
        default = workbook.active
        workbook.remove(default)
        self._ensure_template(workbook)
        try:
            workbook.save(self.workbook_path)
        except PermissionError as error:
            raise BodyWorkbookLockedError() from error
        return workbook

    def _ensure_template(self, workbook) -> None:
        self._ensure_sheet(workbook, "Caroserii", COMMON_HEADERS)
        for category, sheet_name in CATEGORY_SHEETS.items():
            fields = ["body_id", *CATEGORY_FIELDS.get(category, [])]
            self._ensure_sheet(workbook, sheet_name, fields)

    def _ensure_sheet(self, workbook, sheet_name: str, headers: List[str]) -> None:
        sheet = workbook[sheet_name] if sheet_name in workbook.sheetnames else workbook.create_sheet(sheet_name)
        existing_headers = [cell.value for cell in sheet[1]]
        if any(existing_headers):
            missing = [header for header in headers if header not in existing_headers]
            if missing:
                start = len(existing_headers) + 1
                for offset, header in enumerate(missing):
                    sheet.cell(row=1, column=start + offset, value=header)
                    self._style_header_cell(sheet.cell(row=1, column=start + offset))
            return
        for column, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=column, value=header)
            self._style_header_cell(cell)
            sheet.column_dimensions[cell.column_letter].width = min(max(len(header) + 2, 14), 34)

    def _style_header_cell(self, cell) -> None:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="344251")

    def _append_row(self, sheet, headers: List[str], data: Dict[str, Any]) -> None:
        existing_headers = [cell.value for cell in sheet[1]]
        row_index = sheet.max_row + 1
        for header in headers:
            if header not in existing_headers:
                continue
            column = existing_headers.index(header) + 1
            sheet.cell(row=row_index, column=column, value=self._excel_value(data.get(header)))

    def _common_row(self, body: ReviewedBody) -> Dict[str, Any]:
        data = body.model_dump(mode="json")
        data["compatible_chassis_ids"] = ";".join(body.compatible_chassis_ids)
        data["warnings"] = "\n".join(body.warnings)
        data["extraction_notes"] = "\n".join(body.extraction_notes)
        return data

    def _category_row(self, body: ReviewedBody, fields: List[str]) -> Dict[str, Any]:
        data = body.model_dump(mode="json")
        return {field: data.get(field) for field in fields}

    def _excel_value(self, value: Any) -> Any:
        if isinstance(value, list):
            return "\n".join(str(item) for item in value if item is not None)
        if isinstance(value, bool):
            return "DA" if value else "NU"
        return value

    def _clean_compare(self, value: Any) -> str:
        return str(value or "").strip().lower()
