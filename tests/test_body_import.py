import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.body_models import BodyExtraction, ReviewedBody, normalize_category
from app.services.ai_body_parser_service import (
    AIBodyParserService,
    InvalidAIResponseError,
    MissingModelError,
    MissingAPIKeyError,
)
from app.services.body_repository import BodyRepository
from app.services.document_extraction_service import DocumentExtractionService, UnsupportedDocumentError


HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
HAS_DOCX = importlib.util.find_spec("docx") is not None
HAS_REPORTLAB = importlib.util.find_spec("reportlab") is not None
PROJECT_TMP = Path(__file__).resolve().parents[1] / "tmp" / "tests"


def workspace_tmp_path(filename: str) -> Path:
    PROJECT_TMP.mkdir(parents=True, exist_ok=True)
    path = PROJECT_TMP / filename
    path.unlink(missing_ok=True)
    return path


class DocumentExtractionTests(unittest.TestCase):
    @unittest.skipUnless(HAS_PYPDF and HAS_REPORTLAB, "pypdf/reportlab not installed")
    def test_pdf_extraction(self):
        from reportlab.pdfgen import canvas

        path = workspace_tmp_path("supplier.pdf")
        pdf = canvas.Canvas(str(path))
        pdf.drawString(72, 720, "Oferta caroserie frigorifica pentru ISUZU M27 H")
        pdf.drawString(72, 700, "Dimensiuni exterioare 4200 x 2200 x 2300 mm")
        pdf.save()

        text = DocumentExtractionService(PROJECT_TMP, 20_000_000).extract_text(path)
        path.unlink(missing_ok=True)

        self.assertIn("caroserie frigorifica", text.lower())
        self.assertIn("M27 H", text)

    @unittest.skipUnless(HAS_DOCX, "python-docx not installed")
    def test_docx_extraction(self):
        from docx import Document

        path = workspace_tmp_path("supplier.docx")
        document = Document()
        document.add_paragraph("Oferta platforma cu obloane pentru ISUZU M30 K")
        document.add_paragraph("Pret 12000 EUR fara TVA, garantie 24 luni")
        document.save(path)

        text = DocumentExtractionService(PROJECT_TMP, 20_000_000).extract_text(path)
        path.unlink(missing_ok=True)

        self.assertIn("platforma", text.lower())
        self.assertIn("12000", text)

    def test_unsupported_doc(self):
        with self.assertRaises(UnsupportedDocumentError):
            DocumentExtractionService(Path("."), 20_000_000).extract_text(Path("legacy.doc"))


class AIParserTests(unittest.TestCase):
    def test_missing_api_key(self):
        parser = AIBodyParserService("test-model", api_key="")
        with self.assertRaises(MissingAPIKeyError):
            parser.parse("Oferta furnizor cu suficient text pentru procesare.")

    def test_missing_model(self):
        parser = AIBodyParserService("", api_key="test-key")
        with self.assertRaises(MissingModelError):
            parser.parse("Oferta furnizor cu suficient text pentru procesare.")

    def test_malformed_ai_response(self):
        class FakeResponses:
            def create(self, **kwargs):
                return SimpleNamespace(output_text="not-json")

        parser = AIBodyParserService(
            "test-model",
            api_key="test-key",
            client=SimpleNamespace(responses=FakeResponses()),
        )

        with self.assertRaises(InvalidAIResponseError):
            parser.parse("Oferta furnizor cu suficient text pentru procesare.")

    def test_valid_structured_response_with_null_fields(self):
        payload = {
            "categorie": "caroserie termoizolata cu instalatie frigorifica",
            "denumire": "Caroserie frigorifica",
            "furnizor": "Supplier SRL",
            "masa_caroserie_kg": None,
            "warnings": ["Nu a fost identificata masa caroseriei."],
        }

        body = BodyExtraction.model_validate(payload)

        self.assertEqual(body.categorie, "Frigorifica")
        self.assertIsNone(body.masa_caroserie_kg)
        self.assertEqual(body.warnings, ["Nu a fost identificata masa caroseriei."])

    def test_category_parsing(self):
        self.assertEqual(normalize_category("platforma cu obloane"), "Platforma")
        self.assertEqual(normalize_category("bena basculabila trilateral"), "Basculanta")
        self.assertEqual(normalize_category("macara hidraulica"), "Macara")

    def test_compatibility_preselection(self):
        from app.main import _preselected_chassis_ids

        body = BodyExtraction.model_validate(
            {"model_sasiu_referinta": "M27", "cod_ampatament_referinta": "H"}
        )
        selected = _preselected_chassis_ids(body)

        self.assertTrue(any("M27" in sasiu_id and "H" in sasiu_id for sasiu_id in selected))


class BodyRepositoryTests(unittest.TestCase):
    def test_excel_save_sequential_id_and_duplicate_detection(self):
        path = workspace_tmp_path("bodies.xlsx")
        repository = BodyRepository(path)
        body = ReviewedBody.model_validate(
            {
                "categorie": "Frigorifica",
                "denumire": "Caroserie frigorifica",
                "furnizor": "Supplier SRL",
                "nr_oferta_furnizor": "OF-123",
                "data_oferta": "2026-08-08",
                "model_sasiu_referinta": "M27",
                "cod_ampatament_referinta": "H",
                "pret_eur_fara_tva": 12000,
                "compatible_chassis_ids": ["M27_H"],
                "document_sursa": "uploads/body_offers/BODY_IMPORT_20260808_001.pdf",
            }
        )

        first_id = repository.save_body(body)
        second_id = repository.next_body_id()
        duplicate = repository.find_duplicate(body.model_dump(mode="json"))
        path.unlink(missing_ok=True)

        self.assertEqual(first_id, "BODY-0001")
        self.assertEqual(second_id, "BODY-0002")
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate["body_id"], "BODY-0001")


if __name__ == "__main__":
    unittest.main()
