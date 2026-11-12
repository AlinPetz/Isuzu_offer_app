from pathlib import Path
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - app remains usable without dotenv.
    load_dotenv = None


def _external_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundled_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _external_base_dir())).resolve()
    return _external_base_dir()


BASE_DIR = _external_base_dir()
BUNDLED_BASE_DIR = _bundled_base_dir()
ENV_PATH = BASE_DIR / ".env"


def load_environment() -> bool:
    if load_dotenv is None:
        return False
    return bool(load_dotenv(dotenv_path=ENV_PATH, override=True))


def get_openai_api_key() -> str:
    load_environment()
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    load_environment()
    return os.getenv("OPENAI_MODEL", "").strip()


def openai_config_diagnostics() -> dict:
    api_key = get_openai_api_key()
    model = get_openai_model()
    return {
        "env_path": str(ENV_PATH),
        "env_exists": ENV_PATH.exists(),
        "python_dotenv_available": load_dotenv is not None,
        "openai_api_key_configured": bool(api_key),
        "openai_model_configured": bool(model),
        "frozen": bool(getattr(sys, "frozen", False)),
        "base_dir": str(BASE_DIR),
    }


load_environment()

APP_DIR = BUNDLED_BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
OFFERS_DIR = BASE_DIR / "offers"
UPLOADS_DIR = BASE_DIR / "uploads"
BODY_OFFERS_UPLOAD_DIR = UPLOADS_DIR / "body_offers"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

WORKBOOK_PATH = BASE_DIR / Path(os.getenv("ISUZU_WORKBOOK_PATH") or DATA_DIR / "Info_sasie_V2.xlsx")
BODY_WORKBOOK_PATH = DATA_DIR / "ISUZU_Caroserii_Database_Template.xlsx"

APP_NAME = "ISUZU Offer Generator"
OPENAI_API_KEY = get_openai_api_key()
OPENAI_MODEL = get_openai_model()
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
