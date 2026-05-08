"""
LLM Client — Thin wrapper around OpenAI SDK for LM Studio communication.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from openai import OpenAI

from src.config import get_config

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Communicates with Gemma 4 running on LM Studio via the
    OpenAI-compatible API at localhost:1234.
    """

    def __init__(self):
        cfg = get_config().llm
        self._client = OpenAI(
            base_url=cfg.base_url,
            api_key="lm-studio",  # LM Studio doesn't require a real key
        )
        self._model = cfg.model
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_tokens
        self._timeout = cfg.timeout_seconds
        self._retry_attempts = cfg.retry_attempts
        self._retry_delay = cfg.retry_delay_seconds
        self._json_mode_supported = True  # Will auto-disable if LM Studio rejects it

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request to the local LLM.

        Args:
            system_prompt: System-level instructions.
            user_prompt: The main prompt content.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            json_mode: If True, request JSON response format.

        Returns:
            The LLM's response text.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature or self._temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }

        # Try json_mode if requested (some LM Studio versions don't support it)
        use_json_format = json_mode and self._json_mode_supported
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                logger.debug(
                    "LLM request attempt %d/%d (model=%s, json_mode=%s)",
                    attempt, self._retry_attempts, self._model, use_json_format,
                )
                response = self._client.chat.completions.create(
                    **kwargs,
                    timeout=self._timeout,
                )
                content = response.choices[0].message.content
                logger.debug("LLM response received (%d chars)", len(content))
                return content

            except Exception as e:
                err_str = str(e)
                # Detect json_object format not supported — disable and retry immediately
                if use_json_format and ("response_format" in err_str or "json_object" in err_str):
                    logger.warning(
                        "LM Studio does not support response_format json_object — "
                        "disabling and retrying without it"
                    )
                    self._json_mode_supported = False
                    use_json_format = False
                    kwargs.pop("response_format", None)
                    continue  # Retry immediately without counting against attempts

                last_error = e
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s",
                    attempt, self._retry_attempts, e,
                )
                if attempt < self._retry_attempts:
                    time.sleep(self._retry_delay)

        raise ConnectionError(
            f"LLM unavailable after {self._retry_attempts} attempts: {last_error}"
        )

    def analyze_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
    ) -> Dict[str, Any]:
        """
        Send a chat request expecting a JSON response.
        Parses the response and returns the dict.
        """
        # If json_mode isn't supported, reinforce JSON instruction in the prompt
        effective_prompt = user_prompt
        if not self._json_mode_supported:
            effective_prompt = (
                user_prompt
                + "\n\nIMPORTANT: You MUST respond with ONLY valid JSON. "
                "No markdown, no explanation — just the raw JSON object."
            )

        raw = self.chat(
            system_prompt=system_prompt,
            user_prompt=effective_prompt,
            temperature=temperature,
            json_mode=True,
        )

        # Try to parse JSON — handle markdown code fences if LLM wraps them
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Strip markdown code fences
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        # If response contains mixed text + JSON, try to extract the JSON block
        if not cleaned.startswith("{"):
            start_idx = cleaned.find("{")
            if start_idx != -1:
                # Find the matching closing brace
                depth = 0
                for i, ch in enumerate(cleaned[start_idx:], start=start_idx):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            cleaned = cleaned[start_idx : i + 1]
                            break

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response: %s\nRaw: %s", e, raw[:500])
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

    def is_available(self) -> bool:
        """Check if LM Studio is reachable and the model is loaded."""
        try:
            models = self._client.models.list()
            available = [m.id for m in models.data]
            logger.info("LM Studio models available: %s", available)
            return len(available) > 0
        except Exception as e:
            logger.warning("LM Studio not reachable: %s", e)
            return False
