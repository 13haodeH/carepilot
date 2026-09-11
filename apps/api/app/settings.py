import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(
    Path(os.getenv("CARE_PILOT_ENV_FILE", Path(__file__).resolve().parents[1] / ".env.local")),
    override=False,
)


@dataclass(frozen=True)
class RuntimeSettings:
    api_key: str | None
    base_url: str
    model: str
    vision_model: str
    input_usd_per_million: float
    output_usd_per_million: float


def runtime_settings() -> RuntimeSettings:
    """Read server-only model settings at invocation time, never from the browser."""
    deepseek_key = os.getenv("DEEPSEEK_API_KEY") or None
    if deepseek_key:
        return RuntimeSettings(
            api_key=deepseek_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            # Text-only DeepSeek models cannot inspect uploaded images. Keep the
            # vision model explicit and separate from the resolution model.
            vision_model=os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-v4-flash-vision-exp"),
            # Peak, cache-miss list prices. Billing can vary with time/cache, so
            # a project owner may override these server-only estimates.
            input_usd_per_million=float(os.getenv("DEEPSEEK_INPUT_USD_PER_MILLION", "0.44")),
            output_usd_per_million=float(os.getenv("DEEPSEEK_OUTPUT_USD_PER_MILLION", "1.32")),
        )
    return RuntimeSettings(
        api_key=os.getenv("OPENAI_API_KEY") or None,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini-2025-04-14"),
        vision_model=os.getenv("OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini-2025-04-14")),
        input_usd_per_million=float(os.getenv("OPENAI_INPUT_USD_PER_MILLION", "0.40")),
        output_usd_per_million=float(os.getenv("OPENAI_OUTPUT_USD_PER_MILLION", "1.60")),
    )


def model_is_configured() -> bool:
    return bool(runtime_settings().api_key)
