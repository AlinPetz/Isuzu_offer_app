from dataclasses import FrozenInstanceError
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, repository
from app.services.optional_service import parse_optional_items
from app.services.pricing_service import calculate_pricing_snapshot, commercial_preview


ROOT = Path(__file__).resolve().parents[1]
CHASSIS = {
    "sasiu_id": "F14_TEST", "model": "F14", "pret_sasiu": "58887.15",
    "pret_transport": 1400, "pto_cod": "\nM140045409-B*", "pto_pret": "2204.25",
}


class CommercialPricingTests(unittest.TestCase):
    def test_every_current_row_prices_from_excel(self):
        rows = repository.load_chassis()
        self.assertEqual(len(rows), 110)
        self.assertEqual({row["model"].split("_")[0].split()[0] for row in rows},
                         {"M21", "M27", "M29", "M30", "F10", "F11", "F12", "F14"})
        for row in rows:
            with self.subTest(chassis=row["sasiu_id"]):
                snap = calculate_pricing_snapshot(row)
                self.assertEqual(snap.base_chassis_eur, Decimal(str(row["pret_sasiu"])))
                self.assertEqual(snap.transport_eur, Decimal(str(row["pret_transport"])))
                self.assertEqual(snap.total_eur, snap.base_chassis_eur + snap.transport_eur)

    def test_invalid_workbook_prices_are_not_substituted(self):
        for field, value in (("pret_transport", None), ("pret_transport", 1000),
                             ("pret_sasiu", None), ("pret_sasiu", "NaN"), ("pret_sasiu", 0)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                calculate_pricing_snapshot({**CHASSIS, field: value})

    def test_discount_boundary_and_decimal_precision(self):
        snap = calculate_pricing_snapshot(CHASSIS, "58887,15", include_pto=True)
        self.assertEqual(snap.total_eur, Decimal("3604.25"))
        for value in ("58887.16", "-0.01", "-0.001", "0.001", "Infinity", "NaN", "1e3"):
            with self.subTest(discount=value), self.assertRaises(ValueError):
                calculate_pricing_snapshot(CHASSIS, value)
        self.assertEqual(calculate_pricing_snapshot(CHASSIS, "0,10").total_eur, Decimal("60287.05"))

    def test_pto_and_manual_optionals(self):
        items = parse_optional_items(["Set lumini", "Suport inclus"], ["0,20", "0"])
        selected = calculate_pricing_snapshot(CHASSIS, ".10", items, include_pto=True)
        unselected = calculate_pricing_snapshot(CHASSIS, ".10", items)
        self.assertEqual(selected.total_eur - unselected.total_eur, Decimal("2204.25"))
        self.assertEqual(selected.total_eur, Decimal("62491.50"))
        self.assertEqual(len(selected.manual_optionals), 2)
        self.assertEqual(selected.pdf_optionals()[0]["denumire"], "PTO - M140045409-B*")
        self.assertEqual(selected.manual_optionals[1].price_eur, Decimal("0.00"))
        with self.assertRaises(FrozenInstanceError):
            selected.manual_optionals[0].description = "Changed"
        for name in ("PTO", "Priză de putere", "Kit M140045409 B"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "duplicată"):
                calculate_pricing_snapshot(CHASSIS, optionale=parse_optional_items([name], ["20"]), include_pto=True)
        with self.assertRaisesRegex(ValueError, "duplicată"):
            calculate_pricing_snapshot(CHASSIS, optionale=parse_optional_items(["PTO", "Kit M140045409-B*"], ["1", "2"]))

    def test_missing_pto_does_not_disable_chassis_offer(self):
        for row in ({**CHASSIS, "pto_pret": None}, {**CHASSIS, "pto_cod": ""},
                    {**CHASSIS, "pto_cod": None, "pto_pret": None}):
            with self.subTest(row=row):
                self.assertTrue(commercial_preview(row)["pto_warning"])
                self.assertFalse(calculate_pricing_snapshot(row).pto_selected)
                with self.assertRaisesRegex(ValueError, "PTO"):
                    calculate_pricing_snapshot(row, include_pto=True)

    def test_manual_items_require_explicit_valid_price_and_description(self):
        for name, price in (("", "0"), ("Lamp", ""), ("Lamp", "-1"),
                            ("Lamp", "NaN"), ("Lamp", "0.001")):
            with self.subTest(name=name, price=price), self.assertRaises(ValueError):
                parse_optional_items([name], [price])
        self.assertEqual(parse_optional_items([""], [""]), [])

    @unittest.skipUnless(shutil.which("node"), "Node is needed for browser preview parity")
    def test_browser_preview_matches_server_and_rejects_invalid_values(self):
        preview = commercial_preview(CHASSIS)
        cases = [
            (".10", True, [("Light", "0,20"), ("Included", "0")]),
            ("58887,15", False, []),
            ("", False, [("Light", "0.01")]),
            ("58887.16", True, []),
            ("0", True, [("Priză de putere", "1")]),
            ("0", False, [("Light", "0.001")]),
        ]
        script = """
import {previewPricing, formatEUR} from './app/static/js/pricing_preview.mjs';
const [commercial, cases] = JSON.parse(process.argv[1]);
console.log(JSON.stringify(cases.map(([discount, pto, rows]) => {
  const result = previewPricing(commercial, discount, pto,
    rows.map(([description, price]) => ({description, price})));
  return result.total === null ? null : [String(result.total), formatEUR(result.total)];
})));
"""
        output = subprocess.check_output(
            ["node", "--input-type=module", "-e", script, json.dumps([preview, cases])],
            cwd=ROOT, text=True, encoding="utf-8",
        )
        for (discount, pto, rows), result in zip(cases, json.loads(output), strict=True):
            try:
                snap = calculate_pricing_snapshot(CHASSIS, discount, parse_optional_items(
                    [item[0] for item in rows], [item[1] for item in rows]), include_pto=pto)
            except ValueError:
                self.assertIsNone(result)
            else:
                self.assertEqual(result[0], str(int(snap.total_eur * 100)))
                self.assertRegex(result[1], r",[0-9]{2}\sEUR$")


class CommercialRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = repository.load_chassis()
        cls.row = next(row for row in cls.rows if row["sasiu_id"] == "F14_13.5_MECHANIC_J_automatic")
        cls.form = {
            "sasiu_id": cls.row["sasiu_id"], "intern_email": "test@example.invalid",
            "commercial_revision": commercial_preview(cls.row)["revision"], "offer_date": "2099-01-01",
        }
        cls.consultant = [{"email": "test@example.invalid"}]

    def test_stale_manipulated_and_invalid_requests_do_not_allocate(self):
        client = TestClient(app)
        with patch("app.main.repository.load_intern_users", return_value=self.consultant), \
             patch("app.main._next_offer_number") as allocate, \
             patch("app.main._save_offer_data") as save, \
             patch("app.main.pdf_service.generate_offer_pdf") as pdf:
            for extra in ({"commercial_revision": "forged"}, {"commercial_revision": ""},
                          {"discount_sasiu": "58888"}, {"family": "M21"},
                          {"include_pto": "true", "denumire_optional": "PTO", "pret_optional_eur": "1"}):
                with self.subTest(extra=extra):
                    self.assertEqual(client.post("/generate-offer", data=self.form | extra).status_code, 400)
            changed = dict(self.row, pret_sasiu=self.row["pret_sasiu"] + 1)
            with patch("app.main.repository.load_chassis", return_value=[changed]):
                self.assertEqual(client.post("/generate-offer", data=self.form).status_code, 400)
            allocate.assert_not_called()
            save.assert_not_called()
            pdf.assert_not_called()

    def test_server_uses_snapshot_and_does_not_reuse_saved_number(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prior = folder / "OF-20990101-001.json"
            prior.write_text('{"previous": true}', encoding="utf-8")
            with patch("app.main.OFFERS_DIR", folder), \
                 patch("app.main.repository.load_intern_users", return_value=self.consultant), \
                 patch("app.main.pdf_service.generate_offer_pdf", return_value=folder / "OF-20990101-002.pdf") as pdf:
                response = TestClient(app).post("/generate-offer", data=self.form | {
                    "include_pto": "true", "discount_sasiu": "0.10",
                    "denumire_optional": ["Lumini", "Suport"], "pret_optional_eur": ["0.20", "0"],
                    "pret_sasiu": "1", "pret_transport": "0", "pto_pret": "1", "total_fara_tva": "0",
                })
                self.assertEqual(response.status_code, 200)
                saved = json.loads((folder / "OF-20990101-002.json").read_text(encoding="utf-8"))
                snap = saved["pricing_snapshot"]
                self.assertEqual(snap["chassis_id"], self.row["sasiu_id"])
                self.assertEqual(snap["base_chassis_eur"], "58887.00")
                self.assertEqual(snap["transport_eur"], "1400.00")
                self.assertEqual(snap["discount_eur"], "0.10")
                self.assertEqual(snap["pto_code"], "M140045408-B*")
                self.assertTrue(snap["pto_selected"])
                self.assertEqual(snap["pto_price_eur"], "2041.00")
                self.assertEqual(snap["total_eur"], "62328.10")
                self.assertEqual((snap["currency"], snap["excludes_vat"]), ("EUR", True))
                self.assertTrue(snap["calculated_at"].endswith("+00:00"))
                self.assertEqual(snap["manual_optionals"][1]["price_eur"], "0.00")
                self.assertEqual(pdf.call_args.kwargs["pricing"]["total_fara_tva"], Decimal(snap["total_eur"]))
                self.assertEqual(len(pdf.call_args.kwargs["optionale"]), 3)
                self.assertEqual(prior.read_text(encoding="utf-8"), '{"previous": true}')
