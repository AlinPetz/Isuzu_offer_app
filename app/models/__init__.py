from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Chassis(BaseModel):
    sasiu_id: str = ""
    model: str = ""
    display_label: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class Intern(BaseModel):
    nume: str = ""
    telefon: str = ""
    email: str = ""


class ClientInput(BaseModel):
    nume: str = ""
    judet: str = ""
    adresa: str = ""
    email: str = ""
    nr_tel: str = ""
    persoana_contact: str = ""


class OptionalItem(BaseModel):
    denumire: str
    pret_eur: Decimal


class OfferInput(BaseModel):
    sasiu_id: str
    base_model: str = ""
    variation: str = ""
    cab_type: str = ""
    engine: str = ""
    suspension: str = ""
    wheelbase: str = ""
    transmission: str = ""
    intern_email: str
    client: ClientInput
    offer_date: Optional[date] = None
    validity_days: int = 30
    discount_sasiu: Decimal = Decimal("0")
    optionale: list[OptionalItem] = Field(default_factory=list)
