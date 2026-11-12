from typing import Any, Dict, Iterable, List

from app.services.pricing_service import parse_money


def parse_optional_items(names: Iterable[str], prices: Iterable[str]) -> List[Dict[str, Any]]:
    parsed = []
    for index, (raw_name, raw_price) in enumerate(_zip_longest(names, prices), start=1):
        name = str(raw_name or "").strip()
        price_text = str(raw_price or "").strip()
        if not name and not price_text:
            continue
        if not name:
            raise ValueError(f"Denumirea optionalului de pe randul {index} este obligatorie.")
        if not price_text:
            raise ValueError(f"Pretul optionalului '{name}' este obligatoriu.")

        parsed.append({"denumire": name, "pret_eur": parse_money(price_text, f"Prețul opționalului '{name}'")})
    return parsed


def _zip_longest(left: Iterable[str], right: Iterable[str]):
    left_list = list(left or [])
    right_list = list(right or [])
    max_length = max(len(left_list), len(right_list), 0)
    for index in range(max_length):
        yield (
            left_list[index] if index < len(left_list) else "",
            right_list[index] if index < len(right_list) else "",
        )
