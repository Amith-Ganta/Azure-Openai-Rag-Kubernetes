import os

from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()
import re
import json
import openai


# Errors that mean "Azure is unresponsive / unusable right now" and we should
# fall back to the personal OpenAI key. Content-filter blocks are handled
# separately by the guardrail layer and are NOT treated as an outage here.
_AZURE_OUTAGE_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    openai.RateLimitError,
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.NotFoundError,
)


def get_openai_client() -> AzureOpenAI:
    """
    Create Azure OpenAI client.

    Reads AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and
    AZURE_OPENAI_API_VERSION from the environment. Points at the Azure AI
    Foundry resource where the chat + embedding models are deployed.

    Returns:
        Azure OpenAI client.
    """
    return AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    )


def _azure_configured() -> bool:
    """True only if the Azure OpenAI env vars are actually populated."""
    return bool(os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY"))


def get_backup_openai_client() -> OpenAI | None:
    """
    Create the personal (public) OpenAI client used as a backup when Azure
    OpenAI is unresponsive. Returns None if OPENAI_API_KEY is not set, so the
    caller can decide how to degrade.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


class LLMResult(BaseModel):
    """Chat result plus which provider actually answered."""
    content: str
    provider: str  # "azure" | "openai" | "none"


def chat_completion(messages: list[dict], max_completion_tokens: int | None = None) -> LLMResult:
    """
    Resilient chat completion with a provider fallback chain.

    1. Try Azure OpenAI (primary) using AZURE_OPENAI_CHAT_DEPLOYMENT.
    2. If Azure is unconfigured or unresponsive (connection/timeout/5xx/auth/
       rate-limit/not-found), fall back to the personal OpenAI key using
       OPENAI_CHAT_MODEL (default gpt-4o-mini).

    A content-filter BadRequestError is re-raised so the guardrail layer can
    turn it into a refusal rather than silently switching providers.

    Returns:
        LLMResult with the answer text and the provider that served it.
    """
    # --- Primary: Azure OpenAI -------------------------------------------
    if _azure_configured():
        try:
            client = get_openai_client()
            model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini")
            kwargs = {"model": model, "messages": messages}
            if max_completion_tokens:
                kwargs["max_completion_tokens"] = max_completion_tokens
            response = client.chat.completions.create(**kwargs)
            return LLMResult(content=response.choices[0].message.content, provider="azure")
        except openai.BadRequestError:
            # Content filter / malformed request — let the caller (guardrail) decide.
            raise
        except _AZURE_OUTAGE_ERRORS as exc:
            print(f"[fallback] Azure OpenAI unresponsive ({type(exc).__name__}); trying backup OpenAI key.")
        except Exception as exc:  # unknown Azure failure — still try the backup
            print(f"[fallback] Azure OpenAI failed ({type(exc).__name__}: {exc}); trying backup OpenAI key.")
    else:
        print("[fallback] Azure OpenAI not configured; using backup OpenAI key if available.")

    # --- Backup: personal OpenAI key -------------------------------------
    backup = get_backup_openai_client()
    if backup is None:
        raise RuntimeError(
            "Azure OpenAI is unavailable and no OPENAI_API_KEY backup is configured."
        )
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    kwargs = {"model": model, "messages": messages}
    if max_completion_tokens:
        kwargs["max_tokens"] = max_completion_tokens
    response = backup.chat.completions.create(**kwargs)
    return LLMResult(content=response.choices[0].message.content, provider="openai")


def get_structured_completion(
    prompt: str,
    response_model: type[BaseModel],
    model: str | None = None
) -> BaseModel:
    """
    Generate structured output.

    Args:
        prompt: Input prompt.
        response_model: Pydantic response model.
        model: OpenAI model name (e.g. "gpt-4o-mini").

    Returns:
        Parsed response model.
    """
    # Resolve the Azure OpenAI chat deployment name from the environment
    model = model or os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini")


    client = get_openai_client()

    messages = [
        {
            "role": "system",
            "content": "You are an expert financial analyst."
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    # Prefer structured parsing when supported by the deployment
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=response_model
        )

        # Debug: show structured parsed output
        try:
            parsed = response.choices[0].message.parsed
            print("[debug] Structured parsed output:", parsed)
        except Exception:
            print("[debug] Structured response received but could not access parsed field")

        return response.choices[0].message.parsed

    except openai.BadRequestError as exc:
        # Fallback: some Azure deployments/models don't support structured outputs.
        # Request a JSON-only response and parse it with pydantic.
        msg = str(exc)
        if "response_format" in msg or "json_schema" in msg or "Structured Outputs" in msg:
            # Reasoning-style deployments (e.g. gpt-5-mini) need an explicit
            # completion budget so reasoning tokens don't starve the answer, and
            # JSON mode to force a parseable object.
            fallback = client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=4000,
                response_format={"type": "json_object"}
            )

            text = fallback.choices[0].message.content
            print("[debug] Fallback raw text response:\n", text)

            # Try to extract the first JSON object from the model output
            match = re.search(r"\{.*\}", text, re.S)
            json_text = match.group(0) if match else text

            try:
                # Handle explicit 'null' responses: return an empty model instance
                if isinstance(json_text, str) and json_text.strip() in ("null", "None", ""):
                    # Prefer pydantic v2 `model_construct` (no validation) to build an empty model
                    if hasattr(response_model, "model_construct"):
                        return response_model.model_construct()
                    # Fallback: attempt to validate empty dict (may fail if required fields exist)
                    try:
                        return response_model.model_validate({}) if hasattr(response_model, "model_validate") else response_model.parse_obj({})
                    except Exception:
                        raise RuntimeError("Model returned null and cannot construct an empty instance; please check the model schema or use a deployment that supports structured outputs.")

                # Normalize keys so the model's output matches the model's
                # field aliases/names regardless of spacing or casing. Some
                # deployments emit "NetIncome" instead of the alias "Net Income".
                data = json.loads(json_text)
                if isinstance(data, dict):
                    def canon(text: str) -> str:
                        return re.sub(r"[^a-z0-9]", "", str(text).lower())

                    valid_keys = {}
                    for field_name, field in response_model.model_fields.items():
                        valid_keys[canon(field_name)] = field_name
                        if field.alias:
                            valid_keys[canon(field.alias)] = field.alias

                    remapped = {}
                    for key, value in data.items():
                        target = valid_keys.get(canon(key), key)
                        remapped[target] = value
                    data = remapped

                # pydantic v2: model_validate; v1 fallback to parse_obj
                if hasattr(response_model, "model_validate"):
                    parsed = response_model.model_validate(data)
                else:
                    parsed = response_model.parse_obj(data)

                return parsed
            except Exception as e:
                raise RuntimeError(f"Failed to parse JSON fallback response: {e}\nRaw output:\n{text}") from e

        # Re-raise if it's a different bad request
        raise