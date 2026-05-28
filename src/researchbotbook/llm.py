from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


DEFAULT_MODEL = "gpt-4.1-mini"


class LLMClient(Protocol):
    def complete(self, instructions: str, prompt: str) -> str:
        """Return a text completion for the supplied role instructions and prompt."""


@dataclass(frozen=True)
class OpenAIResponsesClient:
    api_key: str
    model: str = DEFAULT_MODEL
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 60

    @classmethod
    def from_env(cls, model: str | None = None) -> "OpenAIResponsesClient":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for --llm")
        return cls(
            api_key=api_key,
            model=model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

    def complete(self, instructions: str, prompt: str) -> str:
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": prompt,
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API request failed: {details}") from exc

        text = extract_response_text(data)
        if not text:
            raise RuntimeError("OpenAI API response did not contain text output")
        return text


def extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


def clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, round(score, 3)))
