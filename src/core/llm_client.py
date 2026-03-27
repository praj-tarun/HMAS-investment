"""LLM client — routes agent calls to the appropriate OpenAI model by layer tier."""

import json
import os
import time
from typing import Optional
import openai
from dotenv import load_dotenv

# Load .env file if present (no-op if not found)
load_dotenv()


# Model tier assignments
LAYER_MODELS = {
    "layer1": "gpt-4o-mini",  # Filtering + extraction (fast, cheap)
    "layer2": "gpt-4o",       # Synthesis + conflict detection
    "layer3": "o3-mini",      # Final reasoning — high-accuracy
}

# Reasoning models use max_completion_tokens and do not accept temperature
_REASONING_MODELS = {"o3-mini", "o3", "o1", "o1-mini", "o1-preview"}


class LLMClient:
    """OpenAI SDK wrapper. Single entry point for all agent LLM calls."""

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError(
                "OPENAI_API_KEY not set.\n"
                "  Set env var:  export OPENAI_API_KEY=sk-...\n"
                "  Or pass:      HMASWorkflow(api_key='sk-...')"
            )
        self.client = openai.OpenAI(api_key=key)

    def reason(
        self,
        system_prompt: str,
        user_message: str,
        layer: str = "layer1",
        max_tokens: int = 2048,
        _retry: int = 0,
    ) -> dict:
        """
        Call OpenAI with a structured reasoning prompt.

        Returns parsed JSON dict. On parse failure returns an error dict that
        preserves the raw response — agents degrade gracefully rather than crash.
        Includes exponential backoff for rate limit errors (up to 3 retries).

        JSON mode (response_format: json_object) is enabled for all layers.
        Layer 3 uses o3-mini (reasoning model) with max_completion_tokens.
        """
        model = LAYER_MODELS.get(layer, LAYER_MODELS["layer1"])
        is_reasoning = model in _REASONING_MODELS

        system_full = (
            system_prompt
            + "\n\n---\n"
            "OUTPUT RULE: Return ONLY a valid JSON object. "
            "No markdown fences, no preamble, no trailing text. "
            "Your response must begin with '{' and end with '}'."
        )

        messages = [
            {"role": "system", "content": system_full},
            {"role": "user", "content": user_message},
        ]

        try:
            # response_format: json_object ensures valid JSON output
            # Reasoning models (o3-mini) use max_completion_tokens, not max_tokens
            kwargs = {
                "model": model,
                "messages": messages,
                "response_format": {"type": "json_object"},
            }
            if is_reasoning:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens

            response = self.client.chat.completions.create(**kwargs)

        except openai.RateLimitError as exc:
            # Distinguish between quota exhausted (no credits) and actual rate limit
            err_body = getattr(exc, "body", {}) or {}
            err_code = err_body.get("error", {}).get("code", "")
            if err_code == "insufficient_quota":
                msg = (
                    "OpenAI quota exhausted — no credits remaining.\n"
                    "  Add credits at: https://platform.openai.com/settings/billing\n"
                    "  Then re-run:    python run.py portfolio --save"
                )
                print(f"\n  [BILLING] {msg}\n")
                return {
                    "error": "insufficient_quota",
                    "reasoning_chain": [msg],
                    "signals": [],
                    "dominant_direction": "neutral",
                    "confidence": "low",
                }
            # True rate limit — retry with exponential backoff
            if _retry < 3:
                wait = 20 * (2 ** _retry)  # 20, 40, 80 seconds (respects 3 RPM free tier)
                print(f"  [RATE LIMIT] Waiting {wait}s before retry {_retry + 1}/3...")
                time.sleep(wait)
                return self.reason(system_prompt, user_message, layer, max_tokens, _retry + 1)
            return {
                "error": f"Rate limit exceeded after 3 retries: {exc}",
                "reasoning_chain": ["Rate limit — reduce request frequency or upgrade OpenAI tier."],
                "signals": [],
                "dominant_direction": "neutral",
                "confidence": "low",
            }
        except openai.APIError as exc:
            return {
                "error": f"API error: {exc}",
                "reasoning_chain": [f"API ERROR: {exc}"],
                "signals": [],
                "dominant_direction": "neutral",
                "confidence": "low",
            }

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences defensively if model ignores the instruction
        if raw.startswith("```"):
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    raw = part
                    break

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "error": str(exc),
                "raw_response": raw[:800],
                "reasoning_chain": [f"PARSE ERROR: LLM response was not valid JSON — {exc}"],
                "signals": [],
                "dominant_direction": "neutral",
                "confidence": "low",
            }
