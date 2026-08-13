"""Free-first HTTP model fabric for OpenClaw."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelEndpoint:
    endpoint_id: str
    provider: str
    model: str
    base_url: str
    api_key_env: str = ""
    free: bool = True
    local: bool = False
    capabilities: List[str] = field(default_factory=list)
    verified: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _request_json(url: str, *, method: str = "GET", headers: Optional[Dict[str, str]] = None, body: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Accept": "application/json", "User-Agent": "GlacierEQ-OpenClaw/3.2", **(headers or {})}
    if payload is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(1024).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc


class ModelFabric:
    def __init__(self, ollama_host: Optional[str] = None):
        self.ollama_host = (ollama_host or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
        self.endpoints: Dict[str, ModelEndpoint] = {}

    def discover_ollama(self, timeout: float = 3.0) -> List[ModelEndpoint]:
        try:
            payload = _request_json(f"{self.ollama_host}/api/tags", timeout=timeout)
        except Exception:
            return []
        discovered: List[ModelEndpoint] = []
        for row in payload.get("models", []) if isinstance(payload, dict) else []:
            if not isinstance(row, dict):
                continue
            model = str(row.get("name") or row.get("model") or "").strip()
            if not model:
                continue
            slug = model.replace("/", "_").replace(":", "_").replace(" ", "_")
            endpoint = ModelEndpoint(
                endpoint_id=f"ollama-{slug}",
                provider="ollama",
                model=model,
                base_url=self.ollama_host,
                free=True,
                local=True,
                capabilities=["chat", "reasoning", "code", "local"],
                verified=True,
                metadata={"digest": row.get("digest"), "size": row.get("size")},
            )
            self.endpoints[endpoint.endpoint_id] = endpoint
            discovered.append(endpoint)
        return discovered

    def register_openai_compatible(self, endpoint_id: str, provider: str, model: str, base_url: str, *, api_key_env: str = "", free: bool = False, local: bool = False, capabilities: Optional[List[str]] = None) -> ModelEndpoint:
        endpoint = ModelEndpoint(
            endpoint_id=endpoint_id,
            provider=provider,
            model=model,
            base_url=base_url.rstrip("/"),
            api_key_env=api_key_env,
            free=free,
            local=local,
            capabilities=list(capabilities or ["chat", "reasoning", "code"]),
        )
        self.endpoints[endpoint_id] = endpoint
        return endpoint

    def probe(self, endpoint: ModelEndpoint, timeout: float = 8.0) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            if endpoint.provider == "ollama":
                payload = _request_json(f"{endpoint.base_url}/api/tags", timeout=timeout)
                models = {str(row.get("name") or row.get("model")) for row in payload.get("models", [])}
                endpoint.verified = endpoint.model in models
            else:
                headers = self._auth_headers(endpoint)
                _request_json(f"{endpoint.base_url}/models", headers=headers, timeout=timeout)
                endpoint.verified = True
            return {"status": "verified" if endpoint.verified else "failed", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except Exception as exc:
            endpoint.verified = False
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    def _auth_headers(self, endpoint: ModelEndpoint) -> Dict[str, str]:
        if not endpoint.api_key_env:
            return {}
        key = os.getenv(endpoint.api_key_env, "")
        if not key:
            raise RuntimeError(f"{endpoint.api_key_env}_NOT_SET")
        return {"Authorization": f"Bearer {key}"}

    def chat(self, endpoint: ModelEndpoint, prompt: str, *, system: str = "You are a coding assistant.", timeout: float = 300.0) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            if endpoint.provider == "ollama":
                payload = _request_json(
                    f"{endpoint.base_url}/api/chat",
                    method="POST",
                    body={
                        "model": endpoint.model,
                        "messages": [
                            *([{"role": "system", "content": system}] if system else []),
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                    timeout=timeout,
                )
                message = payload.get("message", {}) if isinstance(payload, dict) else {}
                text = str(message.get("content") or payload.get("response") or "")
                return {
                    "status": "completed" if text.strip() else "failed",
                    "endpoint_id": endpoint.endpoint_id,
                    "provider": endpoint.provider,
                    "model": endpoint.model,
                    "response": text,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "eval_count": payload.get("eval_count"),
                }

            payload = _request_json(
                f"{endpoint.base_url}/chat/completions",
                method="POST",
                headers=self._auth_headers(endpoint),
                body={
                    "model": endpoint.model,
                    "messages": [
                        *([{"role": "system", "content": system}] if system else []),
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=timeout,
            )
            choices = payload.get("choices", []) if isinstance(payload, dict) else []
            text = str(choices[0].get("message", {}).get("content", "")) if choices else ""
            return {
                "status": "completed" if text.strip() else "failed",
                "endpoint_id": endpoint.endpoint_id,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "response": text,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except Exception as exc:
            return {
                "status": "failed",
                "endpoint_id": endpoint.endpoint_id,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "response": "",
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

    def free_first(self) -> List[ModelEndpoint]:
        return sorted(self.endpoints.values(), key=lambda item: (not item.free, not item.local, not item.verified, item.provider, item.model))


__all__ = ["ModelEndpoint", "ModelFabric"]
