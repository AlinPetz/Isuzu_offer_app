from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from openpyxl import load_workbook


CHASSIS_COLUMNS = (
    "sasiu_id",
    "model",
    "generatie",
    "cod_ampatament",
    "ampatament_mm",
    "lungime_autosasiu",
    "lungime_caroserie_min",
    "lungime_caroserie_max",
    "consola_anterioara_sasiu",
    "consola_posterioara_sasiu",
    "inaltime_sasiu",
    "inaltime_cabina",
    "latime_sasiu",
    "latime_cabina",
    "latime_caroserie_max",
    "distanta_axa_anterioara_spate_cabina",
    "latime_cadru_sasiu",
    "ecartament_anterior",
    "ecartament_posterior",
    "inaltime_min_sol",
    "diametru_rotire",
    "masa_autovehicul_in_ordine_mers",
    "masa_axe_anterior",
    "masa_axe_posterior",
    "masa_maxima_admisa",
    "masa_maxima_admisa_axa_anterioara",
    "masa_maxima_admisa_axa_posterioara",
    "masa_remorcabila_cu_sistem_franare",
    "masa_remorcabila_fara_sistem_franare",
    "cutie_viteza",
    "descriere_cutie_viteza",
    "rapoarte_cutie_viteza",
    "raport_marsalier",
    "raport_in_punte",
    "model_motor",
    "descriere_motor",
    "cilindree_motor",
    "putere_motor_kw",
    "putere_motor_cp",
    "cuplu_motor_Nm",
    "norma_poluare",
    "rezervor_motorina",
    "rezervor_adblue",
    "dimensiuni_lonjeroane_sasiu_latime",
    "dimensiuni_lonjeroane_sasiu_inaltime",
    "dimensiuni_lonjeroane_sasiu_grosime",
    "numar_locuri",
    "numar_axe",
    "anvelope_anterioare",
    "anvelope_posterioare",
    "tip_punte_spate",
    "frane_anterior",
    "frane_posterior",
    "info_frane",
    "suspensie_fata",
    "suspensie_spate",
    "diferential_posterior",
    "info_suspensii",
    "tensiune_v",
    "alternator_a",
    "numar_baterii",
    "capacitate_baterie_ah",
    "pto_cod",
    "pto_pret",
    "pret_sasiu",
    "pret_transport",
    "garantie",
    "imagine_sasiu",
)


class ChassisWorkbookError(ValueError):
    pass


class ExcelRepository:
    def __init__(self, workbook_path: Path):
        self.workbook_path = workbook_path

    def load_chassis(self) -> List[Dict[str, Any]]:
        try:
            workbook = load_workbook(self.workbook_path, read_only=True, data_only=True)
            try:
                rows = workbook["sasie"].values
                headers = next(rows, ())
                if len(headers) != len(CHASSIS_COLUMNS) or set(headers) != set(CHASSIS_COLUMNS):
                    raise ChassisWorkbookError("Foaia sasie nu contine cele 68 de coloane V2.")
                chassis = []
                for number, values in enumerate(rows, start=2):
                    if not any(value is not None for value in values):
                        continue
                    row = dict(zip(headers, values))
                    row["excel_row"] = number
                    row["display_label"] = " | ".join(
                        self._clean_text(row[key])
                        for key in ("model", "cod_ampatament", "cutie_viteza", "sasiu_id")
                    )
                    chassis.append(row)
                return chassis
            finally:
                workbook.close()
        except ChassisWorkbookError:
            raise
        except Exception as error:
            raise ChassisWorkbookError("Fisierul Excel V2 sau foaia sasie nu poate fi citita.") from error

    def load_intern_users(self) -> List[Dict[str, str]]:
        rows = self._read_sheet("intern")
        return [
            {
                "nume": self._clean_text(row.get("nume")),
                "telefon": self._clean_text(row.get("telefon")),
                "email": self._clean_text(row.get("email")),
            }
            for row in rows
        ]

    def _read_sheet(self, sheet_name: str) -> List[Dict[str, Any]]:
        if not self.workbook_path.exists():
            return []

        try:
            dataframe = pd.read_excel(
                self.workbook_path,
                sheet_name=sheet_name,
                engine="openpyxl",
            )
        except ValueError:
            return []
        dataframe = dataframe.rename(columns=lambda value: str(value).strip())
        dataframe = dataframe.where(pd.notna(dataframe), None)

        records: List[Dict[str, Any]] = []
        for record in dataframe.to_dict(orient="records"):
            records.append(
                {
                    str(key).strip(): self._clean_value(value)
                    for key, value in record.items()
                }
            )

        return records

    @staticmethod
    def _clean_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned else None
        return value

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()
