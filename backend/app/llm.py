from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv


load_dotenv()


class LLMNotConfiguredError(RuntimeError):
    """Raised when the optional QC explanation model is not configured."""


def get_llm_settings() -> tuple[str, str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("QC_LLM_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or os.getenv("QC_LLM_BASE_URL", "").strip()
    base_url = base_url.rstrip("/")
    model = os.getenv("OPENAI_MODEL", "").strip() or os.getenv("QC_LLM_MODEL", "gpt-4o-mini").strip()
    if not api_key or not base_url:
        raise LLMNotConfiguredError("QC explanation LLM is not configured")
    return api_key, base_url, model


def is_auto_explain_enabled() -> bool:
    return os.getenv("QC_LLM_AUTO_EXPLAIN", "false").strip().lower() in {"1", "true", "yes", "on"}


def explain_qc_case(context: dict[str, Any], language: str, question: str | None) -> tuple[str, str]:
    """Generate an explanation only; the persisted decision stays authoritative."""
    api_key, base_url, model = get_llm_settings()
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("The openai package is not installed") from error

    output_language = "Vietnamese" if language == "vi" else "English"
    prompt = f"""You are the Visual QC explanation assistant for an automotive FNS station.
Answer in {output_language}. Use only the JSON facts below.
Do not invent tolerances, material properties, GD&T requirements, severity rules, or safety permissions.
Do not change the decision. State clearly that the decision came from the deterministic mock rule engine.
Explain the inspection concisely for a QC inspector, including detected defect, classification, recommendation, route, test-drive permission, and reason codes.

FACTS:
{context}

QC QUESTION:
{question or 'Explain the current QC recommendation.'}
"""
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=15.0)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a careful automotive QC explanation assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    answer = completion.choices[0].message.content or "No explanation was returned."
    return answer, model
