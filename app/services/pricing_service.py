from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re
import unicodedata
from typing import Any, Dict, Iterable


MONEY_ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MONEY_INPUT = re.compile(r"-?(?:[0-9]{1,12}(?:[.,][0-9]{1,2})?|[.,][0-9]{1,2})")
TRANSPORT_COSTS = {
    "M21": Decimal("1000"),
    "M27": Decimal("1000"),
    "M29": Decimal("1000"),
    "M30": Decimal("1000"),
    "F10": Decimal("1400"),
    "F11": Decimal("1400"),
    "F12": Decimal("1400"),
    "F14": Decimal("1400"),
}


def get_transport_cost(model: str) -> Decimal:
    family = _model_family(model)
    if not family:
        raise ValueError(f"Nu se poate calcula transportul pentru modelul '{model}'.")
    return TRANSPORT_COSTS[family]


def calculate_chassis_total(
    chassis: Dict[str, Any],
    discount_sasiu: Any = 0,
    optionale: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Decimal]:
    return calculate_pricing_snapshot(chassis, discount_sasiu, optionale).pdf_prices()


def parse_money(value: Any, label: str, default: Decimal | None = None) -> Decimal:
    if value is None or str(value).strip() == "":
        if default is not None:
            return default
        raise ValueError(f"{label} lipsește.")
    raw = str(value).strip()
    if not MONEY_INPUT.fullmatch(raw):
        raise ValueError(f"{label}: introduceți o sumă în EUR cu maximum două zecimale.")
    money = Decimal(raw.replace(",", "."))
    if money < MONEY_ZERO:
        raise ValueError(f"{label} nu poate fi negativ.")
    return money.quantize(CENT) if money else MONEY_ZERO


def chassis_prices(chassis):
    base = parse_money(chassis.get("pret_sasiu"), "Prețul de bază al șasiului")
    transport = parse_money(chassis.get("pret_transport"), "Prețul transportului")
    expected = get_transport_cost(str(chassis.get("model", "")))
    if base <= 0:
        raise ValueError("Prețul de bază al șasiului trebuie să fie mai mare decât zero.")
    if transport != expected:
        raise ValueError(f"Transportul din Excel ({transport} EUR) nu corespunde regulii familiei ({expected} EUR).")
    return base, transport


def pto_availability(chassis):
    code = str(chassis.get("pto_cod") or "").strip()
    raw_price = chassis.get("pto_pret")
    if code.casefold() in {"", "-", "nan", "none"}:
        message = "Date PTO incomplete: lipsește codul." if raw_price is not None and str(raw_price).strip() else "PTO nu este disponibil în fișa acestui șasiu."
        return None, None, message
    try:
        price = parse_money(raw_price, "Prețul PTO")
        if price > 0 and any(char.isalnum() for char in code):
            return code, price, ""
    except ValueError:
        pass
    return code, None, "Date PTO incomplete sau nevalide: verificați codul și prețul în Excel."


def commercial_preview(chassis):
    base, transport = chassis_prices(chassis)
    code, price, warning = pto_availability(chassis)
    # Bind the preview to the source record, including changes beyond its commercial fields.
    source = {key: value for key, value in chassis.items() if key not in {"excel_row", "display_label"}}
    revision = sha256(json.dumps(source, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "base": str(base), "transport": str(transport), "pto_code": code,
        "pto_price": None if price is None else str(price), "pto_warning": warning,
        "revision": revision,
    }


def _is_pto_item(name, code):
    text = unicodedata.normalize("NFKD", name.casefold())
    words = re.findall(r"[a-z0-9]+", "".join(char for char in text if not unicodedata.combining(char)))
    compact = re.sub(r"[^a-z0-9]", "", (code or "").casefold())
    return (
        "pto" in words or "priza de putere" in " ".join(words)
        or bool(compact and compact in "".join(words))
    )


@dataclass(frozen=True)
class OptionalLine:
    description: str
    price_eur: Decimal


@dataclass(frozen=True)
class PricingSnapshot:
    chassis_id: str
    base_chassis_eur: Decimal
    transport_eur: Decimal
    discount_eur: Decimal
    pto_selected: bool
    pto_code: str | None
    pto_price_eur: Decimal | None
    manual_optionals: tuple[OptionalLine, ...]
    total_eur: Decimal
    calculated_at: datetime
    currency: str = "EUR"
    excludes_vat: bool = True

    def pdf_optionals(self):
        items = [{"denumire": item.description, "pret_eur": item.price_eur} for item in self.manual_optionals]
        if self.pto_selected:
            items.insert(0, {"denumire": f"PTO - {self.pto_code}", "pret_eur": self.pto_price_eur})
        return items

    def pdf_prices(self):
        return {
            "pret_sasiu_baza": self.base_chassis_eur,
            "pret_transport": self.transport_eur,
            "pret_sasiu": self.base_chassis_eur + self.transport_eur,
            "discount_sasiu": self.discount_eur,
            "total_optionale": sum((item["pret_eur"] for item in self.pdf_optionals()), MONEY_ZERO),
            "total_fara_tva": self.total_eur,
            "subtotal_fara_tva": self.total_eur,
        }

    def as_payload(self):
        return {**asdict(self), "calculated_at": self.calculated_at.isoformat()}


def calculate_pricing_snapshot(chassis, discount_sasiu=0, optionale=None, *, include_pto=False):
    base, transport = chassis_prices(chassis)
    discount = parse_money(discount_sasiu, "Discountul șasiului", default=MONEY_ZERO)
    if discount > base:
        raise ValueError("Discountul nu poate depăși prețul de bază al șasiului.")
    code, pto_price, warning = pto_availability(chassis)
    if include_pto and pto_price is None:
        raise ValueError(warning)

    manual = []
    manual_pto = False
    for item in optionale or ():
        name = str(item.get("denumire") or "").strip()
        if not name:
            raise ValueError("Denumirea echipamentului opțional este obligatorie.")
        if _is_pto_item(name, code):
            if include_pto or manual_pto:
                raise ValueError("PTO este inclus de mai multe ori. Eliminați linia duplicată.")
            manual_pto = True
        manual.append(OptionalLine(name, parse_money(item.get("pret_eur"), f"Prețul opționalului '{name}'")))
    total = base + transport - discount + sum((item.price_eur for item in manual), MONEY_ZERO)
    if include_pto:
        total += pto_price
    return PricingSnapshot(
        str(chassis.get("sasiu_id") or "").strip(), base, transport, discount,
        include_pto, code, pto_price, tuple(manual), total, datetime.now(timezone.utc),
    )


def _model_family(model: str) -> str:
    for family in sorted(TRANSPORT_COSTS, key=len, reverse=True):
        if re.match(rf"^{family}(?![0-9])", str(model).strip(), re.I):
            return family
    return ""
