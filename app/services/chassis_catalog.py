from collections import defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from app.config import STATIC_DIR
from app.services.pricing_service import commercial_preview


FIELDS = {
    "family": "Familie model",
    "variant": "Model / varianta",
    "engine_choice": "Motorizare",
    "gearbox": "Transmisie",
    "wheelbase_choice": "Ampatament",
}
FAMILY = re.compile(r"^(M21|M27|M29|M30|F10|F11|F12|F14)(?![0-9])", re.I)
GEARBOX_FIELDS = (
    "generatie", "model", "model_motor", "cilindree_motor", "putere_motor_kw",
    "cod_ampatament", "ampatament_mm", "descriere_cutie_viteza", "rapoarte_cutie_viteza",
)


def _text(value):
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in {"-", "nan", "none"} else text


def _number(value):
    try:
        result = Decimal(_text(value).replace(",", "."))
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _join(*values):
    return " | ".join(value for value in values if value)


def _selection(row):
    model = _text(row["model"])
    generation = _text(row["generatie"])
    family_match = FAMILY.match(model)
    family = family_match.group().upper() if family_match else ""
    length = _text(row["ampatament_mm"])
    engine = _join(
        _text(row["model_motor"]),
        f"{_text(row['cilindree_motor'])} cm³" if _text(row["cilindree_motor"]) else "",
        _text(row["putere_motor_kw"]) or _text(row["putere_motor_cp"]),
    )
    gearbox = _join(_text(row["cutie_viteza"]), _text(row["descriere_cutie_viteza"]))
    return {
        "family": family,
        "variant": _join(model, f"Gen. {generation}" if generation else ""),
        "engine_choice": engine,
        "gearbox": gearbox,
        "wheelbase_choice": _join(_text(row["cod_ampatament"]), f"{length} mm" if length else ""),
    }


def _gearbox_signature(row):
    return tuple(" ".join(_text(row[key]).casefold().split()) for key in GEARBOX_FIELDS)


def _review_fingerprint(row, signature, peers):
    evidence = [
        "gearbox-classification-v1", _text(row["sasiu_id"]), signature,
        _text(row["cutie_viteza"]), _text(row["pto_cod"]), _text(row["pto_pret"]),
        sorted((_text(peer["sasiu_id"]), _text(peer["cutie_viteza"])) for peer in peers),
    ]
    return sha256(json.dumps(evidence, ensure_ascii=False).encode("utf-8")).hexdigest()


class ChassisCatalog:
    def __init__(self, rows, approvals=()):
        self.rows = rows
        self.approvals = set(approvals)
        self.by_id = defaultdict(list)
        self.by_gearbox = defaultdict(list)
        for row in rows:
            self.by_id[_text(row["sasiu_id"])].append(row)
            self.by_gearbox[_gearbox_signature(row)].append(row)
        self.records = [self._record(row) for row in rows]
        self.by_row = {record["excel_row"]: record for record in self.records}

    def _record(self, row):
        chassis_id = _text(row["sasiu_id"])
        selection = _selection(row)
        family = selection["family"]
        generation = _number(row["generatie"])
        errors, warnings, reviews = [], [], []
        if not chassis_id:
            errors.append("Lipseste ID-ul sasiului.")
        elif len(self.by_id[chassis_id]) > 1:
            locations = ", ".join(str(item["excel_row"]) for item in self.by_id[chassis_id])
            errors.append(f"ID duplicat: {chassis_id} (randurile {locations}).")
        if not family or generation != (2 if family == "M27" else 4):
            errors.append("Familia sau generatia nu este acceptata in catalogul V2.")
        if not _text(row["cod_ampatament"]) or (_number(row["ampatament_mm"]) or 0) <= 0:
            errors.append("Codul sau lungimea ampatamentului nu este valida.")
        commercial = None
        if family:
            try:
                commercial = commercial_preview(row)
            except ValueError as error:
                errors.append(str(error))
        for actual, limit in (
            ("masa_axe_anterior", "masa_maxima_admisa_axa_anterioara"),
            ("masa_axe_posterior", "masa_maxima_admisa_axa_posterioara"),
        ):
            mass, maximum = _number(row[actual]), _number(row[limit])
            if mass is not None and maximum is not None and mass > maximum:
                errors.append(f"{actual}: {mass} kg depaseste limita de {maximum} kg. Verificare necesara.")
        front, rear, running = (
            _number(row[key])
            for key in ("masa_axe_anterior", "masa_axe_posterior", "masa_autovehicul_in_ordine_mers")
        )
        if None not in (front, rear, running) and front + rear != running:
            warnings.append(f"Totalul maselor pe axe difera cu {front + rear - running:+} kg. Verificati datele.")
        image = _text(row["imagine_sasiu"])
        if not image or not (STATIC_DIR / "images" / image).is_file():
            warnings.append(f"Imaginea sasiului lipseste: {image or 'fara referinta in Excel'}.")
        signature = _gearbox_signature(row)
        peers = self.by_gearbox[signature]
        transmission = _text(row["cutie_viteza"]).casefold()
        conflicting = [
            peer for peer in peers
            if _text(peer["cutie_viteza"]).casefold() and _text(peer["cutie_viteza"]).casefold() != transmission
        ]
        fingerprint = None
        if not transmission or not all(signature[-2:]):
            warnings.append("Datele transmisiei sunt incomplete.")
        elif conflicting:
            fingerprint = _review_fingerprint(row, signature, peers)
            if fingerprint not in self.approvals:
                ids = ", ".join(_text(peer["sasiu_id"]) for peer in conflicting)
                reviews.append(f"Aceeasi descriere si aceleasi rapoarte de transmisie, dar tip diferit fata de {ids}. Confirmati transmisia si PTO.")
        label = _join(
            chassis_id or "Fara ID",
            f"Rand {row['excel_row']}" if errors or reviews else "",
            f"Masa maxima: {_text(row['masa_maxima_admisa'])} kg" if _text(row["masa_maxima_admisa"]) else "",
            _text(row["suspensie_spate"]),
        )
        return {
            **selection, "sasiu_id": chassis_id, "excel_row": row["excel_row"],
            "label": label, "errors": errors, "warnings": warnings, "reviews": reviews,
            "review_fingerprint": fingerprint,
            "commercial": commercial,
        }

    def payload(self):
        return {
            "fields": [{"key": key, "label": label} for key, label in FIELDS.items()],
            "records": self.records,
        }

    def select(self, chassis_id, selection):
        matches = self.by_id.get(chassis_id.strip(), [])
        if len(matches) != 1:
            locations = ", ".join(str(row["excel_row"]) for row in matches)
            raise ValueError(
                f"ID duplicat: {chassis_id} (randurile {locations})."
                if matches else "Selectati un ID de sasiu valid."
            )
        row = matches[0]
        record = self.by_row[row["excel_row"]]
        if record["errors"]:
            raise ValueError(" ".join(record["errors"]))
        if record["reviews"]:
            raise ValueError("Verificare manuala necesara: " + " ".join(record["reviews"]))
        if any(value and value != (record[key] or "__unspecified__") for key, value in selection.items()):
            raise ValueError("Configuratia selectata nu mai corespunde sasiului din Excel.")
        return row
