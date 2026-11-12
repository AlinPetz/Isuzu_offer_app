from datetime import date
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Tuple
import unicodedata

from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image as PlatypusImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import BASE_DIR, STATIC_DIR


ISUZU_RED = colors.HexColor("#E60012")
DARK_GRAY = colors.HexColor("#344251")
MID_GRAY = colors.HexColor("#848E9A")
LINE_GRAY = colors.HexColor("#D8DDE3")
ROW_GRAY = colors.HexColor("#F6F7F9")
WHITE = colors.white
PDF_IMAGE_CACHE_DIR = BASE_DIR / "cache" / "pdf_images"
DEFAULT_PDF_IMAGE_MAX_SIZE = (1200, 800)
DEFAULT_JPEG_QUALITY = 85

TECHNICAL_FIELD_UNITS = {
    "ampatament_mm": "mm",
    "lungime_autosasiu": "mm",
    "lungime_caroserie_min": "mm",
    "lungime_caroserie_max": "mm",
    "inaltime_sasiu": "mm",
    "latime_cabina": "mm",
    "latime_caroserie_max": "mm",
    "diametru_rotire": "m",
    "dimensiuni_lonjeroane_sasiu_latime": "mm",
    "dimensiuni_lonjeroane_sasiu_inaltime": "mm",
    "dimensiuni_lonjeroane_sasiu_grosime": "mm",
    "cilindree_motor": "cm³",
}


@dataclass(frozen=True)
class PreparedPdfImage:
    path: Path
    source_size: Tuple[int, int]
    embedded_size: Tuple[int, int]
    output_format: str
    quality: int | None


def prepare_image_for_pdf(
    source_path: Path,
    cache_dir: Path = PDF_IMAGE_CACHE_DIR,
    max_size: Tuple[int, int] = DEFAULT_PDF_IMAGE_MAX_SIZE,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> PreparedPdfImage:
    source_path = Path(source_path)
    stat = source_path.stat()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(
        "|".join(
            [
                str(source_path.resolve()),
                str(stat.st_mtime_ns),
                str(stat.st_size),
                f"{max_size[0]}x{max_size[1]}",
                str(jpeg_quality),
            ]
        ).encode("utf-8")
    ).hexdigest()[:24]

    with PILImage.open(source_path) as original:
        image = ImageOps.exif_transpose(original)
        source_size = image.size
        has_alpha = _image_has_transparency(image)
        output_format = "PNG" if has_alpha else "JPEG"
        extension = ".png" if has_alpha else ".jpg"
        cache_path = cache_dir / f"{source_path.stem}-{cache_key}{extension}"

        if cache_path.exists():
            with PILImage.open(cache_path) as cached:
                return PreparedPdfImage(
                    path=cache_path,
                    source_size=source_size,
                    embedded_size=cached.size,
                    output_format=output_format,
                    quality=None if output_format == "PNG" else jpeg_quality,
                )

        prepared = image.copy()
        prepared.thumbnail(max_size, PILImage.Resampling.LANCZOS)

        if output_format == "PNG":
            prepared.save(cache_path, format="PNG", optimize=True)
        else:
            if prepared.mode not in ("RGB", "L"):
                background = PILImage.new("RGB", prepared.size, "white")
                if "A" in prepared.getbands():
                    background.paste(prepared, mask=prepared.getchannel("A"))
                    prepared = background
                else:
                    prepared = prepared.convert("RGB")
            prepared.save(
                cache_path,
                format="JPEG",
                quality=jpeg_quality,
                optimize=True,
                progressive=True,
            )

        return PreparedPdfImage(
            path=cache_path,
            source_size=source_size,
            embedded_size=prepared.size,
            output_format=output_format,
            quality=None if output_format == "PNG" else jpeg_quality,
        )


def _image_has_transparency(image: PILImage.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255
    if image.mode == "P" and "transparency" in image.info:
        return True
    return False


class OfferPdfService:
    def __init__(self, offers_dir: Path):
        self.offers_dir = offers_dir
        self.font_name = _preferred_font()
        self.styles = self._build_styles()

    def generate_offer_pdf(
        self,
        offer_number: str,
        offer_date: date,
        client: Dict[str, Any],
        intern_user: Dict[str, Any],
        chassis: Dict[str, Any],
        pricing: Dict[str, float],
        valabilitate_zile: int,
        selected_configuration: Dict[str, Any] | None = None,
        optionale: List[Dict[str, Any]] | None = None,
    ) -> Path:
        self.offers_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = self.offers_dir / f"{offer_number}.pdf"

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            rightMargin=1.35 * cm,
            leftMargin=1.35 * cm,
            topMargin=0.65 * cm,
            bottomMargin=0.95 * cm,
            title=f"Oferta comerciala {offer_number}",
        )

        story: List[Any] = []
        story.extend(
            self._cover_page(
                offer_number=offer_number,
                offer_date=offer_date,
                client=client,
                intern_user=intern_user,
                chassis=chassis,
                valabilitate_zile=valabilitate_zile,
                selected_configuration=selected_configuration or {},
            )
        )
        for left_title, right_title in [("Dimensiuni", "Mase"), ("Motor", "Transmisie")]:
            story.extend(
                [
                    self._two_column_row(
                        self._section_box(left_title, self._rows_for_group(chassis, left_title), compact=True),
                        self._section_box(right_title, self._rows_for_group(chassis, right_title), compact=True),
                    ),
                    Spacer(1, 0.05 * cm),
                ]
            )
        story.append(PageBreak())

        for left_title, right_title in [("Rezervoare", "Sasiu")]:
            story.extend(
                [
                    self._two_column_row(
                        self._section_box(left_title, self._rows_for_group(chassis, left_title), compact=True),
                        self._section_box(right_title, self._rows_for_group(chassis, right_title), compact=True),
                    ),
                    Spacer(1, 0.08 * cm),
                ]
            )

        story.extend(
            [
                self._two_column_row(
                    self._section_box(
                        "Frane si suspensii",
                        self._rows_for_group(chassis, "Frane si suspensii"),
                        compact=True,
                    ),
                    self._section_box(
                        "Roti si anvelope",
                        self._rows_for_group(chassis, "Roti si anvelope"),
                        compact=True,
                    )
                    + [Spacer(1, 0.06 * cm)]
                    + self._section_box(
                        "Sistem electric",
                        self._rows_for_group(chassis, "Sistem electric"),
                        compact=True,
                    ),
                ),
                Spacer(1, 0.08 * cm),
                *self._optionale_section(optionale or []),
                self._section(
                    "Preturi",
                    self._price_rows(pricing),
                    highlight_last=True,
                    compact=True,
                ),
                Paragraph("Preturile sunt exprimate in EUR si nu includ TVA.", self.styles["Note"]),
                Spacer(1, 0.12 * cm),
                self._section(
                    "Termeni comerciali",
                    [
                        ("Valabilitate oferta", f"{valabilitate_zile} zile"),
                        ("Garantie", chassis.get("garantie")),
                        (
                            "Livrare",
                            "Termenul de livrare va fi confirmat in functie de disponibilitatea vehiculului.",
                        ),
                    ],
                    compact=True,
                ),
                self._signature_block(),
            ]
        )

        doc.build(story, canvasmaker=FooterCanvas)
        return pdf_path

    def _cover_page(
        self,
        offer_number: str,
        offer_date: date,
        client: Dict[str, Any],
        intern_user: Dict[str, Any],
        chassis: Dict[str, Any],
        valabilitate_zile: int,
        selected_configuration: Dict[str, Any],
    ) -> List[Any]:
        content: List[Any] = [
            Paragraph("ISUZU", self.styles["Logo"]),
            Spacer(1, 0.2 * cm),
            Paragraph("Oferta comerciala", self.styles["CoverTitle"]),
            Paragraph(self._value(chassis.get("model")), self.styles["CoverSubtitle"]),
            Spacer(1, 0.12 * cm),
            self._meta_table(
                [
                    ("Numar oferta", offer_number),
                    ("Data", offer_date.strftime("%d.%m.%Y")),
                    ("Valabilitate", f"{valabilitate_zile} zile"),
                ]
            ),
            Spacer(1, 0.18 * cm),
        ]

        image_path = self._resolve_image_path(chassis.get("imagine_sasiu"))
        if image_path:
            prepared_image = prepare_image_for_pdf(image_path)
            content.extend(
                [
                    PlatypusImage(str(prepared_image.path), width=13.4 * cm, height=3.9 * cm, kind="proportional"),
                    Spacer(1, 0.12 * cm),
                ]
            )

        content.extend(
            [
                self._two_column_row(
                    self._section_box("Date client", client.items(), compact=True),
                    self._section_box("Consultant vanzari", intern_user.items(), compact=True),
                ),
                Spacer(1, 0.18 * cm),
                self._summary_section(
                    "Sumar sasiu",
                    [
                        ("Model", chassis.get("model")),
                        ("ID sasiu", chassis.get("sasiu_id")),
                        ("Model baza", selected_configuration.get("base_model")),
                        ("Varianta", selected_configuration.get("variation") or selected_configuration.get("cab_type")),
                        ("Motorizare", selected_configuration.get("engine")),
                        ("Suspensie", selected_configuration.get("suspension")),
                        ("Cod ampatament", chassis.get("cod_ampatament")),
                        ("Ampatament", self.format_technical_value("ampatament_mm", chassis.get("ampatament_mm"))),
                        ("Transmisie", selected_configuration.get("transmission")),
                        (
                            "Masa maxima admisa",
                            self.format_technical_value("masa_maxima_admisa", chassis.get("masa_maxima_admisa")),
                        ),
                        ("Putere motor", chassis.get("putere_motor_cp")),
                        ("Cutie viteze", chassis.get("cutie_viteza")),
                        ("Norma poluare", chassis.get("norma_poluare")),
                    ],
                ),
            ]
        )
        return content

    def _build_styles(self):
        styles = getSampleStyleSheet()
        for style in styles.byName.values():
            style.fontName = self.font_name

        styles.add(
            ParagraphStyle(
                name="Logo",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=28,
                leading=32,
                textColor=ISUZU_RED,
                spaceAfter=0,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CoverTitle",
                parent=styles["Title"],
                fontName="Helvetica",
                fontSize=25,
                leading=30,
                textColor=DARK_GRAY,
                alignment=0,
                spaceAfter=4,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CoverSubtitle",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=11.5,
                leading=14,
                textColor=MID_GRAY,
                spaceAfter=0,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SectionTitle",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=11.5,
                leading=14,
                textColor=ISUZU_RED,
                spaceBefore=0,
                spaceAfter=5,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CellLabel",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=7.6,
                leading=9.2,
                textColor=DARK_GRAY,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CellValue",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=7.6,
                leading=9.2,
                textColor=DARK_GRAY,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CellLabelCompact",
                parent=styles["CellLabel"],
                fontSize=7.1,
                leading=8.2,
            )
        )
        styles.add(
            ParagraphStyle(
                name="CellValueCompact",
                parent=styles["CellValue"],
                fontSize=7.1,
                leading=8.2,
            )
        )
        styles.add(
            ParagraphStyle(
                name="Note",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=8.2,
                leading=10,
                textColor=MID_GRAY,
            )
        )
        return styles

    def _section(
        self,
        title: str,
        rows: Iterable[Tuple[str, Any]],
        compact: bool = False,
        highlight_last: bool = False,
    ):
        return KeepTogether(
            [
                Paragraph(title, self.styles["SectionTitle"]),
                HRFlowable(width="100%", thickness=0.6, color=ISUZU_RED, spaceAfter=3),
                self._key_value_table(rows, compact=compact, highlight_last=highlight_last),
                Spacer(1, 0.16 * cm),
            ]
        )

    def _section_box(
        self,
        title: str,
        rows: Iterable[Tuple[str, Any]],
        compact: bool = False,
    ) -> List[Any]:
        return [
            Paragraph(title, self.styles["SectionTitle"]),
            HRFlowable(width="100%", thickness=0.6, color=ISUZU_RED, spaceAfter=3),
            self._key_value_table(rows, narrow=True, compact=compact),
        ]

    def _summary_section(self, title: str, rows: List[Tuple[str, Any]]):
        return KeepTogether(
            [
                Paragraph(title, self.styles["SectionTitle"]),
                HRFlowable(width="100%", thickness=0.6, color=ISUZU_RED, spaceAfter=3),
                self._summary_table(rows),
                Spacer(1, 0.08 * cm),
            ]
        )

    def _two_column_row(self, left_content: List[Any], right_content: List[Any]) -> Table:
        row = Table(
            [[left_content, "", right_content]],
            colWidths=[7.15 * cm, 0.55 * cm, 7.15 * cm],
            hAlign="LEFT",
        )
        row.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return row

    def _meta_table(self, rows: Iterable[Tuple[str, Any]]) -> Table:
        table = self._key_value_table(rows, compact=True)
        table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE_GRAY)]))
        return table

    def _optionale_section(self, optionale: List[Dict[str, Any]]) -> List[Any]:
        if not optionale:
            return []
        rows = [("Denumire optional", "Pret EUR")]
        rows.extend((item.get("denumire"), self._money(item.get("pret_eur", 0))) for item in optionale)
        return [
            self._section("Optionale", rows, compact=True),
            Spacer(1, 0.08 * cm),
        ]

    def _price_rows(self, pricing: Dict[str, Decimal]) -> List[Tuple[str, Any]]:
        rows: List[Tuple[str, Any]] = [
            ("Pret sasiu", self._money(pricing["pret_sasiu"])),
        ]
        if pricing.get("total_optionale", Decimal("0")) > 0:
            rows.append(("Total optionale", self._money(pricing["total_optionale"])))
        if pricing.get("discount_sasiu", Decimal("0")) > 0:
            rows.append(("Discount sasiu", self._money(pricing["discount_sasiu"])))
        rows.extend(
            [
                ("Total fara TVA", self._money(pricing["total_fara_tva"])),
            ]
        )
        return rows

    def _summary_table(self, rows: List[Tuple[str, Any]]) -> Table:
        label_style = self.styles["CellLabelCompact"]
        value_style = self.styles["CellValueCompact"]
        rows = [(label, value) for label, value in rows if not self._is_empty_value(value)]
        table_rows = []
        for index in range(0, len(rows), 2):
            left = rows[index]
            right = rows[index + 1] if index + 1 < len(rows) else ("", "")
            table_rows.append(
                [
                    Paragraph(str(left[0]), label_style),
                    Paragraph(self._value(left[1]), value_style),
                    Paragraph(str(right[0]), label_style),
                    Paragraph(self._value(right[1]), value_style),
                ]
            )
        table = Table(table_rows, colWidths=[2.2 * cm, 5.25 * cm, 2.2 * cm, 5.25 * cm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, ROW_GRAY]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE_GRAY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                ]
            )
        )
        return table

    def _signature_block(self):
        return KeepTogether(
            [
                Paragraph("Semnatura", self.styles["SectionTitle"]),
                HRFlowable(width="100%", thickness=0.6, color=ISUZU_RED, spaceAfter=10),
                HRFlowable(width="38%", thickness=0.35, color=LINE_GRAY, spaceBefore=12, spaceAfter=3),
                Paragraph("Consultant vanzari", self.styles["Note"]),
            ]
        )

    def _key_value_table(
        self,
        rows: Iterable[Tuple[str, Any]],
        narrow: bool = False,
        compact: bool = False,
        highlight_last: bool = False,
    ) -> Table:
        label_style = self.styles["CellLabelCompact" if compact else "CellLabel"]
        value_style = self.styles["CellValueCompact" if compact else "CellValue"]
        table_data = [
            [
                Paragraph(str(label), label_style),
                Paragraph(self._value(value), value_style),
            ]
            for label, value in rows
        ]
        col_widths = [2.55 * cm, 4.6 * cm] if narrow else [4.9 * cm, 10.0 * cm]
        table = Table(table_data, colWidths=col_widths, hAlign="LEFT")
        vertical_padding = 2.2 if compact else 3.5
        style_commands = [
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, ROW_GRAY]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE_GRAY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
        ]
        if highlight_last and table_data:
            last_row = len(table_data) - 1
            style_commands.extend(
                [
                    ("BACKGROUND", (0, last_row), (-1, last_row), colors.HexColor("#FFF3F4")),
                    ("TEXTCOLOR", (0, last_row), (-1, last_row), ISUZU_RED),
                    ("LINEABOVE", (0, last_row), (-1, last_row), 0.6, ISUZU_RED),
                ]
            )
        table.setStyle(TableStyle(style_commands))
        return table

    def _resolve_image_path(self, value: Any) -> Path | None:
        if not value:
            return None
        raw_path = Path(str(value).strip())
        candidates = [
            raw_path,
            STATIC_DIR / "images" / raw_path,
            STATIC_DIR / "images" / raw_path.name,
            BASE_DIR / raw_path,
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _value(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, float) and math.isnan(value):
            return "-"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if str(value).strip().lower() in ("", "-", "nan", "none"):
            return "-"
        return _plain_text(str(value).strip())

    @classmethod
    def _is_empty_value(cls, value: Any) -> bool:
        return cls._value(value) == "-"

    @classmethod
    def format_technical_value(cls, field_name: str, value: Any) -> str:
        display_value = cls._value(value)
        if display_value == "-":
            return display_value

        unit = cls._unit_for_field(field_name)
        if not unit or cls._value_already_has_unit(display_value, unit):
            return display_value
        if not cls._looks_numeric(display_value):
            return display_value
        return f"{display_value} {unit}"

    @classmethod
    def _unit_for_field(cls, field_name: str) -> str | None:
        if field_name in TECHNICAL_FIELD_UNITS:
            return TECHNICAL_FIELD_UNITS[field_name]
        if field_name.startswith("masa_") or "_masa_" in field_name:
            return "kg"
        return None

    @staticmethod
    def _looks_numeric(value: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", value.strip()))

    @staticmethod
    def _value_already_has_unit(value: str, unit: str) -> bool:
        value = value.strip()
        normalized_value = value.lower().replace("³", "3")
        normalized_unit = unit.lower().replace("³", "3")
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_unit)}\b", normalized_value))

    @staticmethod
    def _money(value: Any) -> str:
        amount = Decimal(str(value))
        return f"{amount:,.2f} EUR".replace(",", " ")

    def _rows_for_group(self, chassis: Dict[str, Any], title: str) -> List[Tuple[str, Any]]:
        return [
            (label, self.format_technical_value(key, chassis.get(key)))
            for label, key in self._technical_groups()[title]
        ]

    @staticmethod
    def _technical_pairs() -> List[Tuple[str, str]]:
        return [
            ("Dimensiuni", "Mase"),
            ("Motor", "Transmisie"),
            ("Rezervoare", "Sasiu"),
        ]

    @staticmethod
    def _technical_groups() -> Dict[str, List[Tuple[str, str]]]:
        return {
            "Dimensiuni": [
                ("Lungime autosasiu", "lungime_autosasiu"),
                ("Lungime caroserie min.", "lungime_caroserie_min"),
                ("Lungime caroserie max.", "lungime_caroserie_max"),
                ("Inaltime sasiu", "inaltime_sasiu"),
                ("Latime cabina", "latime_cabina"),
                ("Latime caroserie max.", "latime_caroserie_max"),
            ],
            "Mase": [
                ("Masa in ordine de mers", "masa_autovehicul_in_ordine_mers"),
                ("Masa maxima admisa", "masa_maxima_admisa"),
                ("Masa max. axa fata", "masa_maxima_admisa_axa_anterioara"),
                ("Masa max. axa spate", "masa_maxima_admisa_axa_posterioara"),
                ("Masa remorcabila cu franare", "masa_remorcabila_cu_sistem_franare"),
            ],
            "Motor": [
                ("Model motor", "model_motor"),
                ("Descriere motor", "descriere_motor"),
                ("Cilindree", "cilindree_motor"),
                ("Putere", "putere_motor_cp"),
                ("Cuplu", "cuplu_motor_Nm"),
                ("Norma poluare", "norma_poluare"),
            ],
            "Transmisie": [
                ("Cutie viteze", "cutie_viteza"),
                ("Descriere cutie viteze", "descriere_cutie_viteza"),
                ("Rapoarte cutie viteze", "rapoarte_cutie_viteza"),
                ("Raport marsarier", "raport_marsalier"),
                ("Raport in punte", "raport_in_punte"),
            ],
            "Rezervoare": [
                ("Rezervor motorina", "rezervor_motorina"),
                ("Rezervor AdBlue", "rezervor_adblue"),
            ],
            "Sasiu": [
                ("Latime lonjeroane", "dimensiuni_lonjeroane_sasiu_latime"),
                ("Inaltime lonjeroane", "dimensiuni_lonjeroane_sasiu_inaltime"),
                ("Grosime lonjeroane", "dimensiuni_lonjeroane_sasiu_grosime"),
                ("Numar locuri", "numar_locuri"),
                ("Numar axe", "numar_axe"),
            ],
            "Frane si suspensii": [
                ("Frane fata", "frane_anterior"),
                ("Frane spate", "frane_posterior"),
                ("Info frane", "info_frane"),
                ("Suspensie fata", "suspensie_fata"),
                ("Suspensie spate", "suspensie_spate"),
                ("Info suspensii", "info_suspensii"),
            ],
            "Roti si anvelope": [
                ("Anvelope fata", "anvelope_anterioare"),
                ("Anvelope spate", "anvelope_posterioare"),
                ("Tip punte spate", "tip_punte_spate"),
            ],
            "Sistem electric": [
                ("Tensiune", "tensiune_v"),
                ("Alternator", "alternator_a"),
                ("Numar baterii", "numar_baterii"),
                ("Capacitate baterie", "capacitate_baterie_ah"),
            ],
        }


class FooterCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(page_count)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_footer(self, page_count: int):
        width, _ = A4
        y = 0.72 * cm
        self.saveState()
        self.setStrokeColor(LINE_GRAY)
        self.setLineWidth(0.35)
        self.line(1.35 * cm, y + 0.35 * cm, width - 1.35 * cm, y + 0.35 * cm)
        self.setFont("Helvetica", 7.4)
        self.setFillColor(MID_GRAY)
        self.drawString(1.35 * cm, y, "Alcor Motors - Dealer ISUZU")
        self.drawCentredString(width / 2, y, "www.isuzu.ro")
        self.drawRightString(width - 1.35 * cm, y, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def _preferred_font() -> str:
    return "Helvetica"


def _plain_text(value: str) -> str:
    replacements = {
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "„": '"',
        "’": "'",
        "ș": "s",
        "Ș": "S",
        "ț": "t",
        "Ț": "T",
        "ă": "a",
        "Ă": "A",
        "â": "a",
        "Â": "A",
        "î": "i",
        "Î": "I",
    }
    for source, replacement in replacements.items():
        value = value.replace(source, replacement)
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
