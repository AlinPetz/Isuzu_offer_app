from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from app.repositories.excel_repository import CHASSIS_COLUMNS, ExcelRepository
from app.services.chassis_catalog import ChassisCatalog, FIELDS
from app.services.chassis_review import approve_review, load_approvals


WORKBOOK = Path(__file__).resolve().parents[1] / "data" / "Info_sasie_V2.xlsx"
F14_CASES = {
    "F14_13.5_MECHANIC_J": ("J", 3790, "manuala", "MZW6P 6 trepte", "M140045408-B*", 2041),
    "F14_13.5_MECHANIC_L": ("L", 4360, "manuala", "MZW6P 6 trepte", "M140045409-B*", 2204),
    "F14_13.5_MECHANIC_J_automatic": ("J", 3790, "automata", "NEES2 + KICK DOWN", "M140045408-B*", 2041),
    "F14_13.5_MECHANIC_L_automatic": ("L", 4360, "automata", "NEES2 + KICK DOWN", "M140045409-B*", 2204),
}


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = ExcelRepository(WORKBOOK)
        cls.rows = cls.repository.load_chassis()
        cls.catalog = ChassisCatalog(cls.rows)

    def test_catalogue_loads_all_records_and_leaves_workbook_unchanged(self):
        digest = sha256(WORKBOOK.read_bytes()).digest()
        rows = self.repository.load_chassis()
        self.assertEqual(Counter(row["generatie"] for row in rows), {4: 105, 2: 5})
        self.assertEqual({row["model"] for row in rows if row["generatie"] == 2}, {"M27"})
        self.assertEqual(len(CHASSIS_COLUMNS), 68)
        with WORKBOOK.open("rb") as stream:
            workbook = load_workbook(stream, read_only=True, data_only=True)
            self.assertEqual(workbook.sheetnames, ["sasie", "clienti", "intern", "Verificare_date"])
            source = workbook["sasie"].values
            columns = next(source)
            for row, values in zip(rows, source, strict=True):
                self.assertEqual(tuple(row[key] for key in columns), values)
            workbook.close()
        self.assertEqual(sha256(WORKBOOK.read_bytes()).digest(), digest)

    def test_all_quotable_rows_resolve_to_their_own_source_row(self):
        valid = [record for record in self.catalog.records if not record["errors"] and not record["reviews"]]
        self.assertEqual(len(valid), 110)
        for record in valid:
            with self.subTest(chassis=record["sasiu_id"]):
                selected = self.catalog.select(record["sasiu_id"], {key: record[key] for key in FIELDS})
                self.assertEqual(selected["excel_row"], record["excel_row"])

    def test_all_twelve_f14_pairs_have_separate_variants(self):
        for number in range(83, 95):
            left, right = (self.catalog.by_row[index] for index in (number, number + 12))
            self.assertEqual((left["family"], right["family"]), ("F14", "F14"))
            self.assertNotEqual(left["variant"], right["variant"])
            self.assertNotEqual(left["sasiu_id"], right["sasiu_id"])
        left, right = self.catalog.by_row[87], self.catalog.by_row[99]
        with self.assertRaisesRegex(ValueError, "nu mai corespunde"):
            self.catalog.select(left["sasiu_id"], {"variant": right["variant"]})

    def test_engine_gearbox_and_wheelbase_are_checked_against_id(self):
        selected = self.catalog.by_row[34]
        for key in ("engine_choice", "gearbox", "wheelbase_choice"):
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, "nu mai corespunde"):
                self.catalog.select(selected["sasiu_id"], {key: self.catalog.by_row[41][key]})

    def test_historical_anomalies_are_detected_without_rewriting_rows(self):
        duplicate = dict(self.rows[84], sasiu_id=self.rows[83]["sasiu_id"])
        axle = dict(self.rows[71], masa_axe_anterior=26258)
        image = dict(self.rows[39], imagine_sasiu=None)
        catalogue = ChassisCatalog([self.rows[83], duplicate, axle, image])
        for number in (85, 86):
            self.assertIn("85, 86", " ".join(catalogue.by_row[number]["errors"]))
        self.assertIn("26258 kg", " ".join(catalogue.by_row[73]["errors"]))
        self.assertIn("Imaginea", " ".join(catalogue.by_row[41]["warnings"]))
        self.assertIs(catalogue.select(image["sasiu_id"], {}), image)
        self.assertEqual(axle["masa_axe_anterior"], 26258)

    def test_routes_enforce_validation_before_offer_side_effects(self):
        duplicate = dict(self.rows[84], sasiu_id=self.rows[83]["sasiu_id"])
        axle = dict(self.rows[71], masa_axe_anterior=26258)
        conflicting_manual = dict(self.rows[82], descriere_cutie_viteza=self.rows[84]["descriere_cutie_viteza"])
        rows = [self.rows[83], duplicate, axle, self.rows[84], conflicting_manual, self.rows[108]]
        client = TestClient(app)
        with patch("app.main.repository.load_chassis", return_value=rows), \
             patch("app.main._next_offer_number") as numbering, \
             patch("app.main.pdf_service.generate_offer_pdf") as pdf:
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn("configuratii blocate", page.text)
            for row, expected in zip(rows[:4], ("ID duplicat", "ID duplicat", "26258 kg", "Verificare manuala")):
                response = client.post("/generate-offer", data={"sasiu_id": row["sasiu_id"], "intern_email": "demo@example.invalid"})
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected, response.json()["detail"])
            numbering.assert_not_called()
            pdf.assert_not_called()

    def test_f14_conflicts_are_data_driven_and_approval_is_scoped(self):
        # Recreate the former conflicts in memory, without editing either workbook.
        rows = [
            dict(row, descriere_cutie_viteza=description) if description else row
            for row in self.rows
            for description in [{
                "F14_13.5_MECHANIC_J_automatic": "MZW6P 6 trepte",
                "F14_13.5_MECHANIC_L": "NEES2 + KICK DOWN",
            }.get(row["sasiu_id"])]
        ]
        pending = ChassisCatalog(rows)
        self.assertEqual({r["sasiu_id"] for r in pending.records if r["reviews"]}, set(F14_CASES))
        self.assertFalse(any(r["errors"] for r in pending.records))
        expected = {
            85: ("J", 3790, "MZW6P 6 trepte", "M140045408-B*", 2041),
            86: ("L", 4360, "NEES2 + KICK DOWN", "M140045409-B*", 2204),
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.jsonl"
            for number, values in expected.items():
                record = pending.by_row[number]
                chassis_id = record["sasiu_id"]
                with self.assertRaisesRegex(ValueError, "Verificare manuala"):
                    pending.select(chassis_id, {})
                approve_review(pending, chassis_id, "Test reviewer", "Test gearbox and PTO evidence", path)
                catalogue = ChassisCatalog(rows, load_approvals(path))
                row = catalogue.select(chassis_id, {key: record[key] for key in FIELDS})
                self.assertEqual(
                    (row["cod_ampatament"], int(row["ampatament_mm"]), row["descriere_cutie_viteza"],
                     row["pto_cod"].strip(), row["pto_pret"]), values,
                )
                self.assertEqual(row["cutie_viteza"], "automata")
                self.assertEqual(row["rapoarte_cutie_viteza"], "6.615 - 4.095 - 2.358 - 1.531 - 1.000 - 0.722")
                self.assertEqual((row["pret_sasiu"], row["pret_transport"]), (58887, 1400))
                changed = [dict(r, pto_pret=999) if r is row else r for r in rows]
                with self.assertRaisesRegex(ValueError, "Verificare manuala"):
                    ChassisCatalog(changed, load_approvals(path)).select(chassis_id, {})
                corrected = ChassisCatalog(self.rows, load_approvals(path))
                self.assertIsNone(corrected.by_row[number]["review_fingerprint"])
                self.assertEqual(corrected.select(chassis_id, {})["excel_row"], number)
            with self.assertRaisesRegex(ValueError, "Verificare manuala"):
                catalogue.select(self.catalog.by_row[83]["sasiu_id"], {})
            with self.assertRaisesRegex(ValueError, "nu mai corespunde"):
                catalogue.select(self.catalog.by_row[85]["sasiu_id"], {
                    "wheelbase_choice": self.catalog.by_row[86]["wheelbase_choice"],
                })

    def test_corrected_f14_records_reach_offer_flow_without_approval(self):
        consultant = {"nume": "Demo", "email": "demo@example.invalid"}
        client = TestClient(app)
        with patch("app.main.repository.load_intern_users", return_value=[consultant]), \
             patch("app.main.load_approvals", return_value=set()), \
             patch("app.main._next_offer_number", return_value="OF-TEST"), \
             patch("app.main._save_offer_data"), \
             patch("app.main.pdf_service.generate_offer_pdf", return_value=Path("OF-TEST.pdf")) as pdf:
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertNotIn("configuratii necesita verificare manuala", page.text)
            for chassis_id, values in F14_CASES.items():
                with self.subTest(chassis=chassis_id):
                    record = next(row for row in self.catalog.records if row["sasiu_id"] == chassis_id)
                    response = client.post("/generate-offer", data={
                        "sasiu_id": chassis_id, "intern_email": consultant["email"],
                        "commercial_revision": record["commercial"]["revision"],
                        **{key: record[key] for key in FIELDS},
                    })
                    self.assertEqual(response.status_code, 200)
                    row = pdf.call_args.kwargs["chassis"]
                    self.assertEqual(row["sasiu_id"], chassis_id)
                    self.assertEqual((row["cod_ampatament"], int(row["ampatament_mm"]), row["cutie_viteza"],
                                      row["descriere_cutie_viteza"], row["pto_cod"].strip(), row["pto_pret"]), values)
                    self.assertEqual(row["rapoarte_cutie_viteza"], "6.615 - 4.095 - 2.358 - 1.531 - 1.000 - 0.722")
                    self.assertEqual(str(row["raport_marsalier"]), "6.615")
                    self.assertEqual((row["pret_sasiu"], row["pret_transport"]), (58887, 1400))
                    self.assertIn(values[3], page.text)
            stale = client.post("/generate-offer", data={
                "sasiu_id": "F14_13.5_MECHANIC_J_automatic", "intern_email": consultant["email"],
                "gearbox": "automata | MZW6P 6 trepte",
            })
            self.assertEqual(stale.status_code, 400)
            self.assertEqual(pdf.call_count, 4)

    def test_valid_m27_reaches_existing_offer_flow(self):
        consultant = {"nume": "Demo", "email": "demo@example.invalid"}
        with patch("app.main.repository.load_intern_users", return_value=[consultant]), \
             patch("app.main._next_offer_number", return_value="OF-TEST"), \
             patch("app.main._save_offer_data") as save, \
             patch("app.main.pdf_service.generate_offer_pdf", return_value=Path("OF-TEST.pdf")) as pdf:
            response = TestClient(app).post("/generate-offer", data={
                "sasiu_id": "M27_H", "family": "M27", "intern_email": consultant["email"],
                "commercial_revision": next(
                    record["commercial"]["revision"] for record in self.catalog.records
                    if record["sasiu_id"] == "M27_H"
                ),
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(pdf.call_args.kwargs["chassis"]["sasiu_id"], "M27_H")
            save.assert_called_once()
