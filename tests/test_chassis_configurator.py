import unittest
from decimal import Decimal
from pathlib import Path

from app.services.optional_service import parse_optional_items
from app.services.chassis_configurator import match_chassis
from app.services.pdf_service import OfferPdfService
from app.services.pricing_service import calculate_chassis_total, get_transport_cost


def row(sasiu_id, model, wheelbase, transmission="manuala"):
    return {
        "sasiu_id": sasiu_id,
        "model": model,
        "cod_ampatament": wheelbase,
        "cutie_viteza": transmission,
        "display_label": f"{model} | Ampatament {wheelbase} | {transmission} | {sasiu_id}",
    }


VALID_ROWS = [
    row("M21T_single_E", "M21 T single", "E"),
    row("M21T_single_H", "M21 T single", "H"),
    row("M21T_E", "M21 T", "E"),
    row("M21T_F", "M21 T", "F"),
    row("M21T_H", "M21 T", "H"),
    row("M21T_heavy_E", "M21 T heavy", "E"),
    row("M21T_heavy_E_automatic", "M21 T heavy", "E", "automata"),
    row("M21T_heavy_F", "M21 T heavy", "F"),
    row("M21TT_E", "M21 TT", "E"),
    row("M21TT_F", "M21 TT", "F"),
    row("M21TT_H_automatic", "M21 TT", "H", "automata"),
    row("M21TT_heavy_H", "M21 TT heavy", "H", "automata"),
    row("M27_E", "M27", "E"),
    row("M27_E_automatic", "M27", "E", "automata"),
    row("M27_F", "M27", "F"),
    row("M27_F_automatic", "M27", "F", "automata"),
    row("M27_H", "M27", "H"),
    row("M29_F", "M29", "F"),
    row("M29_F_automatic", "M29", "F", "automata"),
    row("M29_H", "M29", "H"),
    row("M29_H_automatic", "M29", "H", "automata"),
    row("M30_3L_F", "M30_3L", "F"),
    row("M30_3L_F_automatic", "M30_3L", "F", "automata"),
    row("M30_3L_H", "M30_3L", "H"),
    row("M30_3L_H_automatic", "M30_3L", "H", "automata"),
    row("M30_3L_K", "M30_3L", "K"),
    row("M30_3L_K_automatic", "M30_3L", "K", "automata"),
    row("M30_3L_M", "M30_3L", "M"),
    row("M30_5.2L_F", "M30_5.2L", "F"),
    row("M30_5.2L_F_automatic", "M30_5.2L", "F", "automata"),
    row("M30_5.2L_H", "M30_5.2L", "H"),
    row("M30_5.2L_H_automatic", "M30_5.2L", "H", "automata"),
    row("M30_5.2L_K", "M30_5.2L", "K"),
    row("M30_5.2L_K_automatic", "M30_5.2L", "K", "automata"),
    row("M30_5.2L_M", "M30_5.2L", "M"),
    row("M30_5.2L_M_automatic", "M30_5.2L", "M", "automata"),
    row("M30_5.2L_M_CREW", "M30_5.2L_CREW", "M"),
    row("M30_5.2L_M_CREW_automatic", "M30_5.2L_CREW", "M", "automata"),
    row("F10_MECHANIC_H", "F10_MECHANIC", "H"),
    row("F10_PNEUMATIC_J", "F10_PNEUMATIC", "J"),
    row("F10_PNEUMATIC_J_automatic", "F10_PNEUMATIC", "J", "automata"),
    row("F10_PNEUMATIC_K", "F10_PNEUMATIC", "K"),
    row("F10_PNEUMATIC_K_automatic", "F10_PNEUMATIC", "K", "automata"),
    row("F10_PNEUMATIC_M", "F10_PNEUMATIC", "M"),
    row("F10_PNEUMATIC_M_automatic", "F10_PNEUMATIC", "M", "automata"),
    row("F10_PNEUMATIC_N", "F10_PNEUMATIC", "N"),
    row("F10_PNEUMATIC_N_automatic", "F10_PNEUMATIC", "N", "automata"),
]

for base in ("F11", "F12", "F14"):
    VALID_ROWS.extend(
        [
            row(f"{base}_MECHANIC_H", f"{base}_MECHANIC", "H"),
            row(f"{base}_PNEUMATIC_J", f"{base}_PNEUMATIC", "J"),
            row(f"{base}_PNEUMATIC_J_automatic", f"{base}_PNEUMATIC", "J", "automata"),
            row(f"{base}_PNEUMATIC_K", f"{base}_PNEUMATIC", "K"),
            row(f"{base}_PNEUMATIC_K_automatic", f"{base}_PNEUMATIC", "K", "automata"),
            row(f"{base}_PNEUMATIC_M", f"{base}_PNEUMATIC", "M"),
            row(f"{base}_PNEUMATIC_M_automatic", f"{base}_PNEUMATIC", "M", "automata"),
            row(f"{base}_PNEUMATIC_N", f"{base}_PNEUMATIC", "N"),
            row(f"{base}_PNEUMATIC_N_automatic", f"{base}_PNEUMATIC", "N", "automata"),
        ]
    )


class ChassisConfiguratorTests(unittest.TestCase):
    def assert_valid(self, sasiu_id, **selection):
        chassis = match_chassis(VALID_ROWS, sasiu_id, selection)
        self.assertEqual(chassis["sasiu_id"], sasiu_id)

    def assert_invalid(self, sasiu_id, **selection):
        with self.assertRaises(ValueError):
            match_chassis(VALID_ROWS, sasiu_id, selection)

    def test_valid_m21_configurations(self):
        self.assert_valid("M21T_single_E", base_model="M21", variation="M21 T Single", wheelbase="E", transmission="Manual")
        self.assert_valid("M21T_H", base_model="M21", variation="M21 T", wheelbase="H", transmission="Manual")
        self.assert_valid("M21T_heavy_E_automatic", base_model="M21", variation="M21 T Heavy", wheelbase="E", transmission="Automatic")
        self.assert_valid("M21TT_H_automatic", base_model="M21", variation="M21 TT", wheelbase="H", transmission="Automatic")
        self.assert_valid("M21TT_heavy_H", base_model="M21", variation="M21 TT Heavy", wheelbase="H", transmission="Automatic")

    def test_valid_m27_m29_m30_configurations(self):
        self.assert_valid("M27_F_automatic", base_model="M27", wheelbase="F", transmission="Automatic")
        self.assert_valid("M29_H", base_model="M29", wheelbase="H", transmission="Manual")
        self.assert_valid("M30_3L_K_automatic", base_model="M30", cab_type="Single Cab", engine="3.0L", wheelbase="K", transmission="Automatic")
        self.assert_valid("M30_5.2L_M_automatic", base_model="M30", cab_type="Single Cab", engine="5.2L", wheelbase="M", transmission="Automatic")
        self.assert_valid("M30_5.2L_M_CREW", base_model="M30", cab_type="Crew Cab", engine="5.2L", wheelbase="M", transmission="Manual")

    def test_valid_f_series_configurations(self):
        for base in ("F10", "F11", "F12", "F14"):
            self.assert_valid(f"{base}_MECHANIC_H", base_model=base, suspension="Mechanical", wheelbase="H", transmission="Manual")
            self.assert_valid(f"{base}_PNEUMATIC_N_automatic", base_model=base, suspension="Pneumatic", wheelbase="N", transmission="Automatic")

    def test_invalid_configurations(self):
        self.assert_invalid("M21T_single_E", base_model="M21", variation="M21 T Single", wheelbase="E", transmission="Automatic")
        self.assert_invalid("M21T_heavy_F", base_model="M21", variation="M21 T Heavy", wheelbase="F", transmission="Automatic")
        self.assert_invalid("M21TT_E", base_model="M21", variation="M21 TT", wheelbase="E", transmission="Automatic")
        self.assert_invalid("M21TT_H_automatic", base_model="M21", variation="M21 TT", wheelbase="H", transmission="Manual")
        self.assert_invalid("M27_H", base_model="M27", wheelbase="H", transmission="Automatic")
        self.assert_invalid("M30_3L_M", base_model="M30", cab_type="Single Cab", engine="3.0L", wheelbase="M", transmission="Automatic")
        self.assert_invalid("F10_MECHANIC_H", base_model="F10", suspension="Mechanical", wheelbase="J", transmission="Manual")
        self.assert_invalid("F11_MECHANIC_H", base_model="F11", suspension="Mechanical", wheelbase="H", transmission="Automatic")
        self.assert_invalid("F12_PNEUMATIC_N", base_model="F12", suspension="Pneumatic", wheelbase="Q", transmission="Manual")


class PricingTests(unittest.TestCase):
    def test_transport_costs(self):
        self.assertEqual(get_transport_cost("M21 T single"), Decimal("1000"))
        self.assertEqual(get_transport_cost("M30_5.2L"), Decimal("1000"))
        self.assertEqual(get_transport_cost("F11_PNEUMATIC"), Decimal("1400"))
        self.assertEqual(get_transport_cost("F14_foo"), Decimal("1400"))

    def test_unknown_model_returns_validation_error(self):
        with self.assertRaises(ValueError):
            get_transport_cost("NPR")

    def test_discount_row_visibility(self):
        service = OfferPdfService(Path("offers"))
        chassis = {"model": "M21", "pret_sasiu": "10000", "pret_transport": "1000"}
        no_discount = calculate_chassis_total(chassis, "0", [])
        with_discount = calculate_chassis_total(chassis, "100", [])
        self.assertNotIn("Discount sasiu", [label for label, _ in service._price_rows(no_discount)])
        self.assertIn("Discount sasiu", [label for label, _ in service._price_rows(with_discount)])

    def test_multiple_optionals_are_summed(self):
        optionale = parse_optional_items(["PTO", "Rezervor"], ["1200", "500"])
        pricing = calculate_chassis_total({"model": "M30", "pret_sasiu": "20000", "pret_transport": "1000"}, "0", optionale)
        self.assertEqual(pricing["total_optionale"], Decimal("1700.00"))

    def test_empty_optional_rows_are_ignored(self):
        self.assertEqual(parse_optional_items(["", "PTO"], ["", "1200"]), [{"denumire": "PTO", "pret_eur": Decimal("1200.00")}])

    def test_final_total_formula(self):
        optionale = parse_optional_items(["PTO", "Rezervor"], ["1200", "500"])
        pricing = calculate_chassis_total({"model": "F11", "pret_sasiu": "30000", "pret_transport": "1400"}, "1000", optionale)
        self.assertEqual(pricing["pret_sasiu_baza"], Decimal("30000.00"))
        self.assertEqual(pricing["pret_transport"], Decimal("1400.00"))
        self.assertEqual(pricing["pret_sasiu"], Decimal("31400.00"))
        self.assertEqual(pricing["total_fara_tva"], Decimal("32100.00"))

    def test_optional_validation(self):
        with self.assertRaises(ValueError):
            parse_optional_items(["PTO"], [""])
        with self.assertRaises(ValueError):
            parse_optional_items(["PTO"], ["-1"])
        with self.assertRaises(ValueError):
            parse_optional_items([""], ["100"])


class PdfPresentationTests(unittest.TestCase):
    def test_technical_units_are_added_once(self):
        service = OfferPdfService(Path("offers"))
        self.assertEqual(service.format_technical_value("ampatament_mm", "3345"), "3345 mm")
        self.assertEqual(service.format_technical_value("masa_maxima_admisa", "3500"), "3500 kg")
        self.assertEqual(service.format_technical_value("cilindree_motor", "2999"), "2999 cm³")
        self.assertEqual(service.format_technical_value("rezervor_motorina", "100L"), "100L")
        self.assertEqual(service.format_technical_value("tensiune_v", "24V"), "24V")
        self.assertEqual(service.format_technical_value("alternator_a", "90A"), "90A")
        self.assertEqual(service.format_technical_value("capacitate_baterie_ah", "70Ah"), "70Ah")

    def test_summary_empty_values_are_filtered(self):
        service = OfferPdfService(Path("offers"))
        rows = [
            ("Model baza", "M27"),
            ("Varianta", "-"),
            ("Motorizare", ""),
            ("Suspensie", None),
            ("Ampatament", "3345 mm"),
        ]
        table = service._summary_table(rows)
        rendered_labels = [
            cell.getPlainText()
            for row in table._cellvalues
            for cell in row
            if hasattr(cell, "getPlainText")
        ]
        self.assertIn("Model baza", rendered_labels)
        self.assertIn("Ampatament", rendered_labels)
        self.assertNotIn("Varianta", rendered_labels)
        self.assertNotIn("Motorizare", rendered_labels)
        self.assertNotIn("Suspensie", rendered_labels)


if __name__ == "__main__":
    unittest.main()
