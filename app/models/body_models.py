from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


BodyCategory = Literal[
    "Frigorifica",
    "Platforma",
    "Bena fixa",
    "Basculanta",
    "Hooklift",
    "Macara",
    "Box inchis",
    "Prelata",
    "Altele",
]

CATEGORY_VALUES = [
    "Frigorifica",
    "Platforma",
    "Bena fixa",
    "Basculanta",
    "Hooklift",
    "Macara",
    "Box inchis",
    "Prelata",
    "Altele",
]

COMMON_FIELDS = [
    "categorie",
    "subcategorie",
    "denumire",
    "furnizor",
    "nr_oferta_furnizor",
    "data_oferta",
    "model_sasiu_referinta",
    "cod_ampatament_referinta",
    "lungime_exterioara_mm",
    "latime_exterioara_mm",
    "inaltime_exterioara_mm",
    "lungime_interioara_mm",
    "latime_interioara_mm",
    "inaltime_interioara_mm",
    "volum_interior_mc",
    "masa_caroserie_kg",
    "sarcina_utila_estimata_kg",
    "requires_pto",
    "pto_inclus",
    "pto_cod_necesar",
    "pret_eur_fara_tva",
    "termen_executie",
    "garantie",
    "omologare_rar_inclusa",
    "curs_valutar",
    "avans",
    "observatii",
]

FRIGORIFICA_FIELDS = [
    "grosime_panou_fata_mm",
    "grosime_panouri_laterale_mm",
    "grosime_plafon_mm",
    "grosime_podea_mm",
    "material_izolatie",
    "densitate_izolatie_kg_mc",
    "material_podea",
    "usa_laterala",
    "dimensiune_usa_laterala_mm",
    "nr_usi_spate",
    "oblon_ridicator",
    "model_oblon_ridicator",
    "capacitate_oblon_kg",
    "sine_carne",
    "nr_randuri_sine",
    "nr_carlige",
    "capacitate_carlig_kg",
    "agregat_marca",
    "agregat_model",
    "agent_frigorific",
    "putere_racire_0c_w",
    "putere_racire_minus20c_w",
    "putere_incalzire_w",
    "debit_aer_mc_h",
    "compresor",
    "greutate_agregat_kg",
    "certificat_atp",
    "inregistrator_temperatura",
    "dotari_incluse",
]

PLATFORMA_BENA_FIELDS = [
    "material_sasiu_auxiliar",
    "material_rama_contur",
    "material_podea",
    "grosime_podea_mm",
    "material_oblon_fata",
    "inaltime_oblon_fata_mm",
    "material_obloane_laterale",
    "grosime_obloane_laterale_mm",
    "inaltime_obloane_laterale_mm",
    "material_oblon_spate",
    "grosime_oblon_spate_mm",
    "inaltime_oblon_spate_mm",
    "stalpi_detasabili",
    "stalp_mijloc_detasabil",
    "nr_ancore_podea",
    "scara_urcare",
    "lampi_gabarit",
    "aparatori_noroi",
    "bara_anti_biciclisti",
    "perete_protectie_cabina",
    "sistem_inchidere",
    "dotari_incluse",
]

BASCULANTA_FIELDS = [
    "tip_basculare",
    "unghi_basculare_deg",
    "material_podea",
    "grosime_podea_mm",
    "material_obloane",
    "grosime_obloane_mm",
    "inaltime_obloane_mm",
    "deschidere_automata_oblon_spate",
    "stalpi_detasabili",
    "comenzi_din_cabina",
    "cilindru_tip",
    "supapa_siguranta",
    "dotari_incluse",
]

HOOKLIFT_FIELDS = [
    "marca_hooklift",
    "model_hooklift",
    "capacitate_nominala_kg",
    "lungime_echipament_mm",
    "latime_sine_mm",
    "inaltime_carlig_mm",
    "lungime_container_min_mm",
    "lungime_container_max_mm",
    "presiune_hidraulica_bar",
    "rezervor_ulei_l",
    "comenzi_din_cabina",
    "telecomanda",
    "stabilizatori",
    "sistem_siguranta",
    "dotari_incluse",
]

MACARA_FIELDS = [
    "marca_macara",
    "model_macara",
    "greutate_macara_kg",
    "moment_ridicare_tm",
    "nr_extensii_hidraulice",
    "raza_max_orizontala_m",
    "inaltime_maxima_m",
    "capacitate_la_6m_kg",
    "stabilizatori_laterali",
    "comenzi_ambele_parti",
    "telecomanda",
    "dotari_incluse",
]

CATEGORY_FIELDS = {
    "Frigorifica": FRIGORIFICA_FIELDS,
    "Platforma": PLATFORMA_BENA_FIELDS,
    "Bena fixa": PLATFORMA_BENA_FIELDS,
    "Basculanta": BASCULANTA_FIELDS,
    "Hooklift": HOOKLIFT_FIELDS,
    "Macara": MACARA_FIELDS,
}

ALL_CATEGORY_FIELDS = sorted(
    set(
        FRIGORIFICA_FIELDS
        + PLATFORMA_BENA_FIELDS
        + BASCULANTA_FIELDS
        + HOOKLIFT_FIELDS
        + MACARA_FIELDS
    )
)

ALL_BODY_FIELDS = COMMON_FIELDS + [field for field in ALL_CATEGORY_FIELDS if field not in COMMON_FIELDS]
LIST_FIELDS = {"dotari_incluse", "warnings", "extraction_notes"}
BOOL_FIELDS = {
    "requires_pto",
    "pto_inclus",
    "omologare_rar_inclusa",
    "usa_laterala",
    "oblon_ridicator",
    "sine_carne",
    "certificat_atp",
    "inregistrator_temperatura",
    "stalpi_detasabili",
    "stalp_mijloc_detasabil",
    "scara_urcare",
    "lampi_gabarit",
    "aparatori_noroi",
    "bara_anti_biciclisti",
    "perete_protectie_cabina",
    "deschidere_automata_oblon_spate",
    "comenzi_din_cabina",
    "supapa_siguranta",
    "telecomanda",
    "stabilizatori",
    "sistem_siguranta",
    "comenzi_ambele_parti",
}

FIELD_LABELS = {
    field: field.replace("_", " ").capitalize()
    for field in ALL_BODY_FIELDS + ["warnings", "extraction_notes", "document_sursa", "compatible_chassis_ids"]
}

FIELD_LABELS.update(
    {
        "requires_pto": "Necesita PTO",
        "pto_inclus": "PTO inclus",
        "pto_cod_necesar": "Cod PTO necesar",
        "pret_eur_fara_tva": "Pret EUR fara TVA",
        "omologare_rar_inclusa": "Omologare RAR inclusa",
        "compatible_chassis_ids": "Compatibil cu",
        "document_sursa": "Document sursa",
        "warnings": "Avertismente AI",
        "extraction_notes": "Note extractie",
    }
)


def normalize_category(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if "frigo" in lowered or "termo" in lowered or "refriger" in lowered:
        return "Frigorifica"
    if "platform" in lowered or "obloane" in lowered:
        return "Platforma"
    if "bena fixa" in lowered:
        return "Bena fixa"
    if "bascul" in lowered:
        return "Basculanta"
    if "hook" in lowered or "abroll" in lowered:
        return "Hooklift"
    if "macara" in lowered or "crane" in lowered:
        return "Macara"
    if "box" in lowered or "inchis" in lowered:
        return "Box inchis"
    if "prelat" in lowered:
        return "Prelata"
    if text in CATEGORY_VALUES:
        return text
    return "Altele"


class BodyExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categorie: Optional[BodyCategory] = None
    subcategorie: Optional[str] = None
    denumire: Optional[str] = None
    furnizor: Optional[str] = None
    nr_oferta_furnizor: Optional[str] = None
    data_oferta: Optional[date | str] = None
    model_sasiu_referinta: Optional[str] = None
    cod_ampatament_referinta: Optional[str] = None
    lungime_exterioara_mm: Optional[float] = None
    latime_exterioara_mm: Optional[float] = None
    inaltime_exterioara_mm: Optional[float] = None
    lungime_interioara_mm: Optional[float] = None
    latime_interioara_mm: Optional[float] = None
    inaltime_interioara_mm: Optional[float] = None
    volum_interior_mc: Optional[float] = None
    masa_caroserie_kg: Optional[float] = None
    sarcina_utila_estimata_kg: Optional[float] = None
    requires_pto: Optional[bool] = None
    pto_inclus: Optional[bool] = None
    pto_cod_necesar: Optional[str] = None
    pret_eur_fara_tva: Optional[float] = None
    termen_executie: Optional[str] = None
    garantie: Optional[str] = None
    omologare_rar_inclusa: Optional[bool] = None
    curs_valutar: Optional[str] = None
    avans: Optional[str] = None
    observatii: Optional[str] = None

    grosime_panou_fata_mm: Optional[float] = None
    grosime_panouri_laterale_mm: Optional[float] = None
    grosime_plafon_mm: Optional[float] = None
    grosime_podea_mm: Optional[float] = None
    material_izolatie: Optional[str] = None
    densitate_izolatie_kg_mc: Optional[float] = None
    material_podea: Optional[str] = None
    usa_laterala: Optional[bool] = None
    dimensiune_usa_laterala_mm: Optional[str] = None
    nr_usi_spate: Optional[int] = None
    oblon_ridicator: Optional[bool] = None
    model_oblon_ridicator: Optional[str] = None
    capacitate_oblon_kg: Optional[float] = None
    sine_carne: Optional[bool] = None
    nr_randuri_sine: Optional[int] = None
    nr_carlige: Optional[int] = None
    capacitate_carlig_kg: Optional[float] = None
    agregat_marca: Optional[str] = None
    agregat_model: Optional[str] = None
    agent_frigorific: Optional[str] = None
    putere_racire_0c_w: Optional[float] = None
    putere_racire_minus20c_w: Optional[float] = None
    putere_incalzire_w: Optional[float] = None
    debit_aer_mc_h: Optional[float] = None
    compresor: Optional[str] = None
    greutate_agregat_kg: Optional[float] = None
    certificat_atp: Optional[bool] = None
    inregistrator_temperatura: Optional[bool] = None
    dotari_incluse: List[str] = Field(default_factory=list)

    material_sasiu_auxiliar: Optional[str] = None
    material_rama_contur: Optional[str] = None
    material_oblon_fata: Optional[str] = None
    inaltime_oblon_fata_mm: Optional[float] = None
    material_obloane_laterale: Optional[str] = None
    grosime_obloane_laterale_mm: Optional[float] = None
    inaltime_obloane_laterale_mm: Optional[float] = None
    material_oblon_spate: Optional[str] = None
    grosime_oblon_spate_mm: Optional[float] = None
    inaltime_oblon_spate_mm: Optional[float] = None
    stalpi_detasabili: Optional[bool] = None
    stalp_mijloc_detasabil: Optional[bool] = None
    nr_ancore_podea: Optional[int] = None
    scara_urcare: Optional[bool] = None
    lampi_gabarit: Optional[bool] = None
    aparatori_noroi: Optional[bool] = None
    bara_anti_biciclisti: Optional[bool] = None
    perete_protectie_cabina: Optional[bool] = None
    sistem_inchidere: Optional[str] = None

    tip_basculare: Optional[str] = None
    unghi_basculare_deg: Optional[float] = None
    material_obloane: Optional[str] = None
    grosime_obloane_mm: Optional[float] = None
    inaltime_obloane_mm: Optional[float] = None
    deschidere_automata_oblon_spate: Optional[bool] = None
    comenzi_din_cabina: Optional[bool] = None
    cilindru_tip: Optional[str] = None
    supapa_siguranta: Optional[bool] = None

    marca_hooklift: Optional[str] = None
    model_hooklift: Optional[str] = None
    capacitate_nominala_kg: Optional[float] = None
    lungime_echipament_mm: Optional[float] = None
    latime_sine_mm: Optional[float] = None
    inaltime_carlig_mm: Optional[float] = None
    lungime_container_min_mm: Optional[float] = None
    lungime_container_max_mm: Optional[float] = None
    presiune_hidraulica_bar: Optional[float] = None
    rezervor_ulei_l: Optional[float] = None
    telecomanda: Optional[bool] = None
    stabilizatori: Optional[bool] = None
    sistem_siguranta: Optional[bool] = None

    marca_macara: Optional[str] = None
    model_macara: Optional[str] = None
    greutate_macara_kg: Optional[float] = None
    moment_ridicare_tm: Optional[float] = None
    nr_extensii_hidraulice: Optional[int] = None
    raza_max_orizontala_m: Optional[float] = None
    inaltime_maxima_m: Optional[float] = None
    capacitate_la_6m_kg: Optional[float] = None
    comenzi_ambele_parti: Optional[bool] = None

    warnings: List[str] = Field(default_factory=list)
    extraction_notes: List[str] = Field(default_factory=list)

    @field_validator("*", mode="before")
    @classmethod
    def empty_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("categorie", mode="before")
    @classmethod
    def normalize_categorie(cls, value: Any) -> Any:
        return normalize_category(value)


class ReviewedBody(BodyExtraction):
    body_id: Optional[str] = None
    document_sursa: Optional[str] = None
    compatible_chassis_ids: List[str] = Field(default_factory=list)


def body_to_form_data(body: BodyExtraction | ReviewedBody | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(body, BaseModel):
        data = body.model_dump(mode="json")
    else:
        data = dict(body)
    for field in ALL_BODY_FIELDS:
        data.setdefault(field, None)
    data.setdefault("warnings", [])
    data.setdefault("extraction_notes", [])
    data.setdefault("document_sursa", None)
    data.setdefault("compatible_chassis_ids", [])
    return data
