from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.config import get_openai_api_key, get_openai_model
from app.models.body_models import BodyExtraction


SYSTEM_INSTRUCTION = """You are extracting technical and commercial information from a supplier quotation for a commercial vehicle body/superstructure.

Extract only information explicitly supported by the document.

Never invent, estimate or assume technical specifications.

If information is absent, ambiguous or uncertain, return null.

Do not determine chassis compatibility unless the supplier document explicitly identifies the chassis/model/wheelbase.

Do not calculate payload unless explicitly provided.

Do not infer PTO requirements simply because a type of equipment commonly requires PTO.

Do not convert prices unless explicitly necessary.

Distinguish between prices excluding VAT and including VAT.

Return normalized numerical values without unit text where the schema already defines the unit.

Preserve detailed included-equipment descriptions.

Your output will be reviewed by a human before being added to the database."""


class AIParserError(Exception):
    user_message = "Analiza AI nu a putut fi efectuata."


class MissingAPIKeyError(AIParserError):
    user_message = "Lipseste OPENAI_API_KEY. Configurati cheia API in fisierul .env."


class MissingModelError(AIParserError):
    user_message = "Lipseste OPENAI_MODEL. Configurati modelul OpenAI in fisierul .env."


class InvalidAIResponseError(AIParserError):
    user_message = "Raspunsul AI nu a respectat structura asteptata."


class AIUnavailableError(AIParserError):
    user_message = "Documentul a fost incarcat, dar analiza AI nu a putut fi efectuata."


class AIBodyParserService:
    def __init__(self, model: str | None = None, api_key: str | None = None, client: Any | None = None):
        self.model = model
        self.api_key = api_key
        self.client = client

    def parse(self, extracted_text: str) -> BodyExtraction:
        api_key = self.api_key if self.api_key is not None else get_openai_api_key()
        model = self.model if self.model is not None else get_openai_model()
        if not api_key and self.client is None:
            raise MissingAPIKeyError()
        if not model:
            raise MissingModelError()
        if not extracted_text.strip():
            raise InvalidAIResponseError()

        client = self.client or self._build_client(api_key)
        schema = BodyExtraction.model_json_schema()

        try:
            response = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {
                        "role": "user",
                        "content": (
                            "Convert this supplier quotation text into the requested structured "
                            "body/superstructure data. Return null for absent or uncertain fields.\n\n"
                            f"{extracted_text}"
                        ),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "supplier_body_extraction",
                        "schema": schema,
                        "strict": False,
                    }
                },
            )
        except AIParserError:
            raise
        except Exception as error:
            raise AIUnavailableError() from error

        try:
            payload = self._response_json(response)
            return BodyExtraction.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError) as error:
            raise InvalidAIResponseError() from error

    def _build_client(self, api_key: str):
        try:
            from openai import OpenAI
        except ImportError as error:
            raise AIUnavailableError() from error
        return OpenAI(api_key=api_key)

    def _response_json(self, response: Any) -> dict[str, Any]:
        output_text = getattr(response, "output_text", None)
        if not output_text:
            output_text = self._extract_output_text(response)
        if isinstance(output_text, dict):
            return output_text
        return json.loads(output_text)

    def _extract_output_text(self, response: Any) -> str:
        if isinstance(response, dict):
            output = response.get("output", [])
        else:
            output = getattr(response, "output", [])

        for item in output:
            content = item.get("content", []) if isinstance(item, dict) else getattr(item, "content", [])
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    return part["text"]
                text = getattr(part, "text", None)
                if text:
                    return text
        raise InvalidAIResponseError()
