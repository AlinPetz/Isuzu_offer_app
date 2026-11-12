from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


CONFIG_FIELDS = [
    "base_model",
    "variation",
    "cab_type",
    "engine",
    "suspension",
    "wheelbase",
    "transmission",
]


@dataclass(frozen=True)
class ConfigOption:
    key: str
    label: str


FIELD_LABELS = {
    "base_model": "Model de baza",
    "variation": "Varianta",
    "cab_type": "Tip cabina",
    "engine": "Motorizare",
    "suspension": "Suspensie",
    "wheelbase": "Ampatament",
    "transmission": "Transmisie",
}


VALUE_LABELS = {
    "Manual": "Manuala",
    "Automatic": "Automata",
    "Mechanical": "Mecanica",
    "Pneumatic": "Pneumatica",
}


def build_configurator_records(chassis_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    records = []
    for chassis in chassis_rows:
        record = configuration_for_chassis(chassis)
        if not record["base_model"]:
            continue
        records.append(record)
    return records


def configuration_for_chassis(chassis: Dict[str, Any]) -> Dict[str, str]:
    model = _text(chassis.get("model"))
    sasiu_id = _text(chassis.get("sasiu_id"))
    source = f"{model} {sasiu_id}".upper()
    base_model = _base_model(source)

    return {
        "sasiu_id": sasiu_id,
        "display_label": _text(chassis.get("display_label")) or sasiu_id,
        "base_model": base_model,
        "variation": _variation(model, source, base_model),
        "cab_type": _cab_type(source, base_model),
        "engine": _engine(source, base_model),
        "suspension": _suspension(source, base_model),
        "wheelbase": _text(chassis.get("cod_ampatament")),
        "transmission": _transmission(chassis.get("cutie_viteza"), source),
    }


def match_chassis(
    chassis_rows: Iterable[Dict[str, Any]],
    selected_sasiu_id: str,
    selection: Dict[str, str],
) -> Dict[str, Any]:
    rows = list(chassis_rows)
    config_records = build_configurator_records(rows)
    matching_ids = [
        record["sasiu_id"]
        for record in config_records
        if _record_matches_selection(record, selection)
    ]

    if selected_sasiu_id:
        if selected_sasiu_id not in matching_ids:
            raise ValueError(
                "Configuratia selectata nu corespunde cu niciun sasiu valid din baza de date."
            )
        matches = [row for row in rows if _text(row.get("sasiu_id")) == selected_sasiu_id]
    else:
        matches = [row for row in rows if _text(row.get("sasiu_id")) in matching_ids]

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("Nu exista niciun sasiu pentru configuratia selectata.")

    codes = ", ".join(_text(row.get("sasiu_id")) for row in matches)
    raise ValueError(f"Configuratia selectata gaseste mai multe sasiuri: {codes}.")


def option_payload(config_records: Iterable[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "fields": [{"key": key, "label": FIELD_LABELS[key]} for key in CONFIG_FIELDS],
        "value_labels": VALUE_LABELS,
        "records": list(config_records),
    }


def _record_matches_selection(record: Dict[str, str], selection: Dict[str, str]) -> bool:
    for field in CONFIG_FIELDS:
        expected = _text(selection.get(field))
        if expected and _text(record.get(field)) != expected:
            return False
    return True


def _base_model(source: str) -> str:
    for prefix in ("M21", "M27", "M29", "M30", "F10", "F11", "F12", "F14"):
        if source.startswith(prefix) or f" {prefix}" in source:
            return prefix
    return ""


def _variation(model: str, source: str, base_model: str) -> str:
    if base_model != "M21":
        return ""
    normalized = " ".join(model.replace("_", " ").split()).title()
    if "SINGLE" in source:
        return "M21 T Single"
    if "TT HEAVY" in source or "TT_HEAVY" in source:
        return "M21 TT Heavy"
    if "TT" in source:
        return "M21 TT"
    if "HEAVY" in source:
        return "M21 T Heavy"
    return normalized or "M21 T"


def _cab_type(source: str, base_model: str) -> str:
    if base_model != "M30":
        return ""
    if "CREW" in source:
        return "Crew Cab"
    return "Single Cab"


def _engine(source: str, base_model: str) -> str:
    if base_model != "M30":
        return ""
    if "5.2" in source or "5_2" in source or "52L" in source:
        return "5.2L"
    if "3L" in source or "3.0" in source or "3_0" in source:
        return "3.0L"
    return ""


def _suspension(source: str, base_model: str) -> str:
    if not base_model.startswith("F"):
        return ""
    if "PNEUMATIC" in source or "PNEUMAT" in source:
        return "Pneumatic"
    if "MECHANIC" in source or "MECANIC" in source:
        return "Mechanical"
    return ""


def _transmission(value: Any, source: str) -> str:
    text = _text(value).lower()
    if "auto" in text or "AUTOMATIC" in source:
        return "Automatic"
    if text or "MANUAL" in source:
        return "Manual"
    return ""


def _text(value: Optional[Any]) -> str:
    if value is None:
        return ""
    return str(value).strip()
