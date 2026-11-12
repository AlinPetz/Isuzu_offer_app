from datetime import date, datetime
import json
from pathlib import Path
from typing import List
from xml.sax.saxutils import escape

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    APP_NAME,
    BASE_DIR,
    BODY_OFFERS_UPLOAD_DIR,
    BODY_WORKBOOK_PATH,
    MAX_UPLOAD_SIZE_BYTES,
    OFFERS_DIR,
    OPENAI_MODEL,
    STATIC_DIR,
    TEMPLATES_DIR,
    WORKBOOK_PATH,
    openai_config_diagnostics,
)
from app.models.body_models import (
    ALL_BODY_FIELDS,
    BOOL_FIELDS,
    CATEGORY_VALUES,
    FIELD_LABELS,
    LIST_FIELDS,
    ReviewedBody,
    body_to_form_data,
)
from app.repositories.excel_repository import ChassisWorkbookError, ExcelRepository
from app.services.chassis_catalog import ChassisCatalog
from app.services.chassis_review import load_approvals
from app.services.chassis_configurator import configuration_for_chassis
from app.services.ai_body_parser_service import (
    AIBodyParserService,
    AIParserError,
)
from app.services.body_repository import BodyRepository, BodyRepositoryError
from app.services.document_extraction_service import (
    DocumentExtractionError,
    DocumentExtractionService,
    relative_upload_path,
)
from app.services.optional_service import parse_optional_items
from app.services.pdf_service import OfferPdfService
from app.services.pricing_service import PricingSnapshot, calculate_pricing_snapshot, commercial_preview


app = FastAPI(title=APP_NAME)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
repository = ExcelRepository(WORKBOOK_PATH)
pdf_service = OfferPdfService(OFFERS_DIR)
document_extractor = DocumentExtractionService(BODY_OFFERS_UPLOAD_DIR, MAX_UPLOAD_SIZE_BYTES)
body_repository = BodyRepository(BODY_WORKBOOK_PATH)
ai_body_parser = AIBodyParserService()


@app.get("/", response_class=HTMLResponse)
def offer_form(request: Request):
    workbook_error = None
    try:
        catalog = ChassisCatalog(repository.load_chassis(), load_approvals())
        intern_users = repository.load_intern_users()
    except ChassisWorkbookError as error:
        catalog, intern_users = ChassisCatalog([]), []
        workbook_error = str(error)

    return templates.TemplateResponse(
        request=request,
        name="offer_form.html",
        context={
            "configurator": catalog.payload(),
            "workbook_error": workbook_error,
            "intern_users": intern_users,
        },
    )


@app.post("/generate-offer", response_class=HTMLResponse)
def generate_offer(
    request: Request,
    sasiu_id: str = Form(...),
    family: str = Form(""),
    variant: str = Form(""),
    engine_choice: str = Form(""),
    gearbox: str = Form(""),
    wheelbase_choice: str = Form(""),
    intern_email: str = Form(...),
    nume: str = Form(""),
    judet: str = Form(""),
    adresa: str = Form(""),
    email: str = Form(""),
    nr_tel: str = Form(""),
    persoana_contact: str = Form(""),
    offer_date: str = Form(""),
    valabilitate_zile: int = Form(30),
    discount_sasiu: str = Form("0"),
    include_pto: bool = Form(False),
    commercial_revision: str = Form(""),
    denumire_optional: List[str] = Form(default=[]),
    pret_optional_eur: List[str] = Form(default=[]),
):
    selection = {
        "family": family,
        "variant": variant,
        "engine_choice": engine_choice,
        "gearbox": gearbox,
        "wheelbase_choice": wheelbase_choice,
    }
    try:
        chassis = ChassisCatalog(repository.load_chassis(), load_approvals()).select(sasiu_id, selection)
    except ChassisWorkbookError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    intern_user = _find_by_key(repository.load_intern_users(), "email", intern_email)
    if intern_user is None:
        raise HTTPException(status_code=404, detail="Consultantul selectat nu a fost gasit.")

    try:
        if commercial_revision != commercial_preview(chassis)["revision"]:
            raise ValueError("Datele șasiului s-au schimbat sau selecția a expirat. Reîncărcați formularul.")
        parsed_date = _parse_offer_date(offer_date)
        optionale = parse_optional_items(denumire_optional, pret_optional_eur)
        snapshot = calculate_pricing_snapshot(chassis, discount_sasiu, optionale, include_pto=include_pto)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    pricing = snapshot.pdf_prices()
    optionale = snapshot.pdf_optionals()
    client = {
        "nume": nume,
        "judet": judet,
        "adresa": adresa,
        "email": email,
        "nr_tel": nr_tel,
        "persoana_contact": persoana_contact,
    }
    selected_configuration = configuration_for_chassis(chassis)
    offer_number = _next_offer_number(parsed_date)
    try:
        # Reserve the number by saving its immutable inputs before creating the PDF.
        _save_offer_data(
            offer_number=offer_number,
            offer_date=parsed_date,
            client=client,
            intern_user=intern_user,
            chassis=chassis,
            selected_configuration=selected_configuration,
            optionale=optionale,
            pricing=pricing,
            snapshot=snapshot,
            valabilitate_zile=valabilitate_zile,
        )
    except FileExistsError as error:
        raise HTTPException(status_code=409, detail="Numărul ofertei este deja rezervat. Reîncercați.") from error
    pdf_path = pdf_service.generate_offer_pdf(
        offer_number=offer_number,
        offer_date=parsed_date,
        client=client,
        intern_user=intern_user,
        chassis=chassis,
        selected_configuration=selected_configuration,
        optionale=[{**item, "denumire": escape(item["denumire"])} for item in optionale],
        pricing=pricing,
        valabilitate_zile=valabilitate_zile,
    )

    return templates.TemplateResponse(
        request=request,
        name="offer_success.html",
        context={
            "offer_number": offer_number,
            "total_fara_tva": pricing["total_fara_tva"],
            "pdf_filename": pdf_path.name,
        },
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/caroserii", response_class=HTMLResponse)
def body_management(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="body_import.html",
        context={
            "body_home": True,
            "error": None,
            "saved_document": None,
            "openai_model": OPENAI_MODEL,
        },
    )


@app.get("/caroserii/config")
def body_import_config():
    return openai_config_diagnostics()


@app.get("/caroserii/import", response_class=HTMLResponse)
def import_body_form(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="body_import.html",
        context={
            "body_home": False,
            "error": None,
            "saved_document": None,
            "openai_model": OPENAI_MODEL,
        },
    )


@app.post("/caroserii/import", response_class=HTMLResponse)
async def import_body_document(request: Request, supplier_document: UploadFile = File(...)):
    try:
        document_path = await document_extractor.save_upload(supplier_document)
        extracted_text = document_extractor.extract_text(document_path)
        extraction = ai_body_parser.parse(extracted_text)
    except DocumentExtractionError as error:
        return _body_import_error(request, error.user_message)
    except AIParserError as error:
        saved_document = None
        if "document_path" in locals():
            saved_document = relative_upload_path(document_path, BASE_DIR)
        return _body_import_error(request, error.user_message, saved_document=saved_document)

    selected_chassis = _preselected_chassis_ids(extraction)
    return templates.TemplateResponse(
        request=request,
        name="body_review.html",
        context=_body_review_context(
            extraction,
            document_sursa=relative_upload_path(document_path, BASE_DIR),
            selected_chassis_ids=selected_chassis,
        ),
    )


@app.post("/caroserii/import/retry", response_class=HTMLResponse)
async def retry_body_import(request: Request):
    form = await request.form()
    document_sursa = str(form.get("document_sursa") or "")
    try:
        document_path = _resolve_uploaded_document(document_sursa)
        extracted_text = document_extractor.extract_text(document_path)
        extraction = ai_body_parser.parse(extracted_text)
    except (DocumentExtractionError, AIParserError) as error:
        return _body_import_error(request, error.user_message, saved_document=document_sursa)

    selected_chassis = _preselected_chassis_ids(extraction)
    return templates.TemplateResponse(
        request=request,
        name="body_review.html",
        context=_body_review_context(
            extraction,
            document_sursa=document_sursa,
            selected_chassis_ids=selected_chassis,
        ),
    )


@app.post("/caroserii/save", response_class=HTMLResponse)
async def save_body(request: Request):
    form = await request.form()
    body_payload = _body_payload_from_form(form)
    selected_chassis_ids = [str(value) for value in form.getlist("compatible_chassis_ids") if str(value).strip()]
    body_payload["compatible_chassis_ids"] = selected_chassis_ids
    body_payload["document_sursa"] = str(form.get("document_sursa") or "")

    try:
        reviewed_body = ReviewedBody.model_validate(body_payload)
    except Exception as error:
        return templates.TemplateResponse(
            request=request,
            name="body_review.html",
            context=_body_review_context(
                body_payload,
                document_sursa=body_payload["document_sursa"],
                selected_chassis_ids=selected_chassis_ids,
                error="Unele campuri au valori invalide. Verificati formularul si incercati din nou.",
            ),
            status_code=400,
        )

    duplicate = body_repository.find_duplicate(reviewed_body.model_dump(mode="json"))
    confirm_duplicate = str(form.get("confirm_duplicate") or "") == "1"
    if duplicate and not confirm_duplicate:
        return templates.TemplateResponse(
            request=request,
            name="body_review.html",
            context=_body_review_context(
                reviewed_body,
                document_sursa=reviewed_body.document_sursa or "",
                selected_chassis_ids=selected_chassis_ids,
                duplicate_warning="Este posibil ca aceasta oferta sa fi fost deja importata.",
                confirm_duplicate=True,
            ),
        )

    try:
        body_id = body_repository.save_body(reviewed_body)
    except BodyRepositoryError as error:
        return templates.TemplateResponse(
            request=request,
            name="body_review.html",
            context=_body_review_context(
                reviewed_body,
                document_sursa=reviewed_body.document_sursa or "",
                selected_chassis_ids=selected_chassis_ids,
                error=error.user_message,
            ),
            status_code=400,
        )

    return templates.TemplateResponse(
        request=request,
        name="body_saved.html",
        context={
            "body_id": body_id,
            "denumire": reviewed_body.denumire or "-",
            "categorie": reviewed_body.categorie or "-",
            "workbook_path": BODY_WORKBOOK_PATH,
        },
    )


@app.get("/caroserii/lista", response_class=HTMLResponse)
def list_bodies(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="body_saved.html",
        context={
            "bodies": body_repository.list_bodies(),
            "workbook_path": BODY_WORKBOOK_PATH,
        },
    )


@app.get("/download/{filename}")
def download_offer(filename: str):
    safe_name = Path(filename).name
    pdf_path = OFFERS_DIR / safe_name
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="Oferta PDF nu a fost gasita.")
    return FileResponse(pdf_path, media_type="application/pdf", filename=safe_name)


def _find_by_key(items, key: str, value: str):
    for item in items:
        if str(item.get(key, "")).strip() == str(value).strip():
            return item
    return None


def _parse_offer_date(value: str) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _save_offer_data(
    offer_number: str,
    offer_date: date,
    client,
    intern_user,
    chassis,
    selected_configuration,
    optionale,
    pricing,
    snapshot: PricingSnapshot,
    valabilitate_zile: int,
):
    OFFERS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "offer_number": offer_number,
        "offer_date": offer_date.isoformat(),
        "valabilitate_zile": valabilitate_zile,
        "selected_chassis_id": chassis.get("sasiu_id"),
        "selected_chassis_code": chassis.get("sasiu_id"),
        "base_model": selected_configuration.get("base_model", ""),
        "variation": selected_configuration.get("variation", ""),
        "cab_type": selected_configuration.get("cab_type", ""),
        "engine": selected_configuration.get("engine", ""),
        "suspension": selected_configuration.get("suspension", ""),
        "wheelbase": selected_configuration.get("wheelbase", ""),
        "transmission": selected_configuration.get("transmission", ""),
        "optionale": optionale,
        "client": client,
        "intern_user": intern_user,
        "pricing": pricing,
        "pricing_snapshot": snapshot.as_payload(),
    }
    with (OFFERS_DIR / f"{offer_number}.json").open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, default=str)


def _next_offer_number(offer_date: date) -> str:
    OFFERS_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"OF-{offer_date:%Y%m%d}-"
    existing_numbers = []
    for path in OFFERS_DIR.glob(f"{prefix}*"):
        if path.suffix.lower() not in {".pdf", ".json"}:
            continue
        suffix = path.stem.removeprefix(prefix)
        if suffix.isdigit():
            existing_numbers.append(int(suffix))
    return f"{prefix}{max(existing_numbers, default=0) + 1:03d}"


def _body_import_error(request: Request, message: str, saved_document: str | None = None):
    return templates.TemplateResponse(
        request=request,
        name="body_import.html",
        context={
            "body_home": False,
            "error": message,
            "saved_document": saved_document,
            "openai_model": OPENAI_MODEL,
        },
        status_code=400,
    )


def _body_review_context(
    extraction,
    document_sursa: str,
    selected_chassis_ids: List[str],
    error: str | None = None,
    duplicate_warning: str | None = None,
    confirm_duplicate: bool = False,
):
    body_data = body_to_form_data(extraction)
    body_data["document_sursa"] = document_sursa
    body_data["compatible_chassis_ids"] = selected_chassis_ids
    form_values = _form_values(body_data)
    return {
        "body_data": body_data,
        "form_values": form_values,
        "document_sursa": document_sursa,
        "field_labels": FIELD_LABELS,
        "category_values": CATEGORY_VALUES,
        "bool_fields": BOOL_FIELDS,
        "list_fields": LIST_FIELDS,
        "field_groups": _body_field_groups(),
        "chassis_options": _chassis_options(),
        "selected_chassis_ids": set(selected_chassis_ids),
        "error": error,
        "duplicate_warning": duplicate_warning,
        "confirm_duplicate": confirm_duplicate,
    }


def _body_field_groups():
    return [
        ("Identificare", ["categorie", "subcategorie", "denumire", "furnizor", "nr_oferta_furnizor", "data_oferta"]),
        ("Compatibilitate sasiu", ["model_sasiu_referinta", "cod_ampatament_referinta"]),
        (
            "Dimensiuni",
            [
                "lungime_exterioara_mm",
                "latime_exterioara_mm",
                "inaltime_exterioara_mm",
                "lungime_interioara_mm",
                "latime_interioara_mm",
                "inaltime_interioara_mm",
                "volum_interior_mc",
            ],
        ),
        ("Mase", ["masa_caroserie_kg", "sarcina_utila_estimata_kg"]),
        ("PTO", ["requires_pto", "pto_inclus", "pto_cod_necesar"]),
        (
            "Pret si conditii comerciale",
            ["pret_eur_fara_tva", "termen_executie", "garantie", "omologare_rar_inclusa", "curs_valutar", "avans"],
        ),
        (
            "Specificatii categorie",
            [
                field
                for field in ALL_BODY_FIELDS
                if field
                not in {
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
                    "dotari_incluse",
                }
            ],
        ),
        ("Dotari", ["dotari_incluse"]),
        ("Observatii", ["observatii", "extraction_notes"]),
        ("Avertismente AI", ["warnings"]),
    ]


def _form_values(data):
    values = {}
    for key, value in data.items():
        if key in LIST_FIELDS and isinstance(value, list):
            values[key] = "\n".join(str(item) for item in value)
        elif value is None:
            values[key] = ""
        else:
            values[key] = value
    return values


def _body_payload_from_form(form) -> dict:
    payload = {}
    for field in ALL_BODY_FIELDS:
        if field in LIST_FIELDS:
            payload[field] = _lines(str(form.get(field) or ""))
            continue
        if field in BOOL_FIELDS:
            payload[field] = _parse_bool(form.get(field))
            continue
        value = form.get(field)
        payload[field] = None if value is None or str(value).strip() == "" else str(value).strip()

    payload["warnings"] = _lines(str(form.get("warnings") or ""))
    payload["extraction_notes"] = _lines(str(form.get("extraction_notes") or ""))
    return payload


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _parse_bool(value):
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "da", "yes"}:
        return True
    if normalized in {"0", "false", "nu", "no"}:
        return False
    return value


def _chassis_options():
    return [
        {
            "sasiu_id": row.get("sasiu_id", ""),
            "label": row.get("display_label") or row.get("model") or row.get("sasiu_id", ""),
            "model": row.get("model", ""),
            "cod_ampatament": row.get("cod_ampatament", ""),
        }
        for row in repository.load_chassis()
    ]


def _preselected_chassis_ids(extraction) -> list[str]:
    data = body_to_form_data(extraction)
    model_ref = str(data.get("model_sasiu_referinta") or "").strip().upper()
    wheelbase_ref = str(data.get("cod_ampatament_referinta") or "").strip().upper()
    if not model_ref and not wheelbase_ref:
        return []
    matches = []
    for chassis in repository.load_chassis():
        model = str(chassis.get("model") or "").upper()
        wheelbase = str(chassis.get("cod_ampatament") or "").upper()
        if model_ref and not model.startswith(model_ref):
            continue
        if wheelbase_ref and wheelbase != wheelbase_ref:
            continue
        matches.append(str(chassis.get("sasiu_id")))
    return matches


def _resolve_uploaded_document(document_sursa: str) -> Path:
    if not document_sursa:
        raise HTTPException(status_code=400, detail="Documentul incarcat nu a fost gasit.")
    candidate = (BASE_DIR / document_sursa).resolve()
    upload_root = BODY_OFFERS_UPLOAD_DIR.resolve()
    if upload_root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Calea documentului este invalida.")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Documentul incarcat nu mai exista.")
    return candidate
