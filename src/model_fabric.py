"""Free-first HTTP model fabric for OpenClaw.

The fabric executes real HTTP model calls and dynamically discovers local and
free endpoints. Secrets are referenced by environment-variable name only.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


KILO_GATEWAY = "https://api.kilo.ai/api/gateway"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_CONFIG = ".openclaw/model-fabric.json"


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
    status: str = "untested"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
) -> Any:
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "GlacierEQ-OpenClaw/3.2",
        **(headers or {}),
    }
    if payload is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc


class ModelFabric:
    def __init__(self, ollama_host: Optional[str] = None, config_path: Optional[str] = None):
        self.ollama_host = (ollama_host or os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA).rstrip("/")
        self.config_path = Path(config_path or os.getenv("OPENCLAW_MODEL_FABRIC") or DEFAULT_CONFIG).expanduser()
        self.endpoints: Dict[str, ModelEndpoint] = {}

    def register(self, endpoint: ModelEndpoint) -> ModelEndpoint:
        self.endpoints[endpoint.endpoint_id] = endpoint
        return endpoint

    def register_openai_compatible(
        self,
        endpoint_id: str,
        provider: str,
        model: str,
        base_url: str,
        *,
        api_key_env: str = "",
        free: bool = False,
        local: bool = False,
        capabilities: Optional[List[str]] = None,
        optional_auth: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> ModelEndpoint:
        return self.register(ModelEndpoint(
            endpoint_id=endpoint_id,
            provider=provider,
            model=model,
            base_url=base_url.rstrip("/"),
            api_key_env=api_key_env,
            free=free,
            local=local,
            capabilities=list(capabilities or ["chat", "reasoning", "code"]),
            metadata={"optional_auth": bool(optional_auth), "headers": dict(headers or {})},
        ))

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
            endpoint = self.register(ModelEndpoint(
                endpoint_id=f"ollama-{slug}",
                provider="ollama",
                model=model,
                base_url=self.ollama_host,
                free=True,
                local=True,
                capabilities=["chat", "reasoning", "code", "local"],
                verified=True,
                status="verified",
                metadata={"digest": row.get("digest"), "size": row.get("size"), "source": "ollama:/api/tags"},
            ))
            discovered.append(endpoint)
        return discovered

    def discover_kilo_free(self, timeout: float = 8.0) -> List[ModelEndpoint]:
        """Discover Kilo Gateway free models, including anonymous-capable routes."""
        headers: Dict[str, str] = {}
        key = os.getenv("KILO_API_KEY", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        discovered: List[ModelEndpoint] = []
        try:
            payload = _request_json(f"{KILO_GATEWAY}/models", headers=headers, timeout=timeout)
        except Exception:
            payload = {}

        rows = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else []
        for row in rows if isinstance(rows, list) else []:
            model_id = str(row.get("id") if isinstance(row, dict) else row).strip()
            if not model_id:
                continue
            is_free = model_id.endswith(":free") or model_id in {"openrouter/free", "kilo-auto/free"}
            if not is_free:
                continue
            slug = model_id.replace("/", "_").replace(":", "_")
            endpoint = self.register_openai_compatible(
                endpoint_id=f"kilo-{slug}",
                provider="kilo-gateway",
                model=model_id,
                base_url=KILO_GATEWAY,
                api_key_env="KILO_API_KEY",
                free=True,
                local=False,
                optional_auth=True,
                capabilities=["chat", "reasoning", "code", "free"],
            )
            endpoint.verified = True
            endpoint.status = "verified"
            endpoint.metadata["source"] = "kilo:/models"
            discovered.append(endpoint)

        auto = self.register_openai_compatible(
            endpoint_id="kilo-auto-free",
            provider="kilo-gateway",
            model="kilo-auto/free",
            base_url=KILO_GATEWAY,
            api_key_env="KILO_API_KEY",
            free=True,
            local=False,
            optional_auth=True,
            capabilities=["chat", "reasoning", "code", "free", "auto-routing"],
        )
        auto.metadata["source"] = "builtin"
        if key:
            auto.status = "configured"
        discovered.append(auto)
        return discovered

    def register_environment_endpoints(self) -> List[ModelEndpoint]:
        """Register well-known providers only when their environment is configured."""
        added: List[ModelEndpoint] = []
        if os.getenv("MIMO_API_KEY"):
            added.append(self.register_openai_compatible(
                endpoint_id="mimo-api",
                provider="mimo",
                model=os.getenv("MIMO_MODEL", "mimo-v2.5-pro"),
                base_url=os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1"),
                api_key_env="MIMO_API_KEY",
                free=False,
                capabilities=["chat", "reasoning", "code", "large-context"],
            ))
        if os.getenv("GROQ_API_KEY"):
            added.append(self.register_openai_compatible(
                endpoint_id="groq-free",
                provider="groq",
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                base_url="https://api.groq.com/openai/v1",
                api_key_env="GROQ_API_KEY",
                free=True,
                capabilities=["chat", "reasoning", "code", "fast"],
            ))
        if os.getenv("OPENROUTER_API_KEY"):
            added.append(self.register_openai_compatible(
                endpoint_id="openrouter-free",
                provider="openrouter",
                model=os.getenv("OPENROUTER_FREE_MODEL", "openrouter/free"),
                base_url="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
                free=True,
                capabilities=["chat", "reasoning", "code", "free", "auto-routing"],
            ))
        return added

    def load_config(self) -> List[ModelEndpoint]:
        if not self.config_path.exists():
            return []
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"invalid model fabric config {self.config_path}: {exc}") from exc
        added: List[ModelEndpoint] = []
        for raw in payload.get("endpoints", []) if isinstance(payload, dict) else []:
            if not isinstance(raw, dict) or raw.get("enabled", True) is False:
                continue
            endpoint_id = str(raw.get("id") or "").strip()
            model = str(raw.get("model") or "").strip()
            base_url = str(raw.get("base_url") or "").strip()
            if not endpoint_id or not model or not base_url:
                continue
            endpoint = self.register_openai_compatible(
                endpoint_id=endpoint_id,
                provider=str(raw.get("provider") or "openai-compatible"),
                model=model,
                base_url=base_url,
                api_key_env=str(raw.get("api_key_env") or ""),
                free=bool(raw.get("free", False)),
                local=bool(raw.get("local", False)),
                capabilities=[str(item) for item in raw.get("capabilities", ["chat", "reasoning", "code"])],
                optional_auth=bool(raw.get("optional_auth", False)),
                headers={str(k): str(v) for k, v in (raw.get("headers") or {}).items()},
            )
            endpoint.metadata["source"] = f"config:{self.config_path}"
            added.append(endpoint)
        return added

    def discover_all(self) -> List[ModelEndpoint]:
        self.endpoints = {}
        self.discover_ollama()
        self.discover_kilo_free()
        self.register_environment_endpoints()
        self.load_config()
        return list(self.endpoints.values())

    def _auth_headers(self, endpoint: ModelEndpoint) -> Dict[str, str]:
        headers = {str(k): str(v) for k, v in endpoint.metadata.get("headers", {}).items()}
        if endpoint.api_key_env:
            key = os.getenv(endpoint.api_key_env, "")
            if key:
                headers["Authorization"] = f"Bearer {key}"
            elif not endpoint.metadata.get("optional_auth", False):
                raise RuntimeError(f"{endpoint.api_key_env}_NOT_SET")
        return headers

    def probe(self, endpoint: ModelEndpoint, timeout: float = 8.0) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            if endpoint.provider == "ollama":
                payload = _request_json(f"{endpoint.base_url}/api/tags", timeout=timeout)
                models = {str(row.get("name") or row.get("model")) for row in payload.get("models", [])}
                endpoint.verified = endpoint.model in models
            else:
                _request_json(f"{endpoint.base_url}/models", headers=self._auth_headers(endpoint), timeout=timeout)
                endpoint.verified = True
            endpoint.status = "verified" if endpoint.verified else "failed"
            return {"status": endpoint.status, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except Exception as exc:
            endpoint.verified = False
            endpoint.status = "failed"
            return {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

    def chat(
        self,
        endpoint: ModelEndpoint,
        prompt: str,
        *,
        system: str = "You are a coding assistant.",
        timeout: float = 300.0,
        mode: str = "code",
    ) -> Dict[str, Any]:
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
                endpoint.verified = bool(text.strip())
                endpoint.status = "verified" if endpoint.verified else "failed"
                return {
                    "status": "completed" if text.strip() else "failed",
                    "endpoint_id": endpoint.endpoint_id,
                    "provider": endpoint.provider,
                    "model": endpoint.model,
                    "response": text,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "eval_count": payload.get("eval_count"),
                }

            headers = self._auth_headers(endpoint)
            if endpoint.provider == "kilo-gateway":
                headers.setdefault("x-kilocode-mode", mode)
            payload = _request_json(
                f"{endpoint.base_url}/chat/completions",
                method="POST",
                headers=headers,
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
            choices = payload.get("choices", []) if isinstance(payload, dict) else []
            text = str(choices[0].get("message", {}).get("content", "")) if choices else ""
            endpoint.verified = bool(text.strip())
            endpoint.status = "verified" if endpoint.verified else "failed"
            return {
                "status": "completed" if text.strip() else "failed",
                "endpoint_id": endpoint.endpoint_id,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "response": text,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "usage": payload.get("usage") if isinstance(payload, dict) else None,
            }
        except Exception as exc:
            endpoint.status = "failed"
            return {
                "status": "failed",
                "endpoint_id": endpoint.endpoint_id,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "response": "",
                "error": f"{type(exc).__name__}: {exc}",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

    def free_first(self, *, verified_only: bool = False) -> List[ModelEndpoint]:
        values = [endpoint for endpoint in self.endpoints.values() if not verified_only or endpoint.verified]
        return sorted(values, key=lambda item: (not item.free, not item.local, not item.verified, item.provider, item.model))

    def route(self, *, prefer_local: bool = True, free_only: bool = True) -> Optional[ModelEndpoint]:
        candidates = [endpoint for endpoint in self.endpoints.values() if (endpoint.free or not free_only)]
        candidates.sort(key=lambda item: (not item.verified, not item.free, (not item.local) if prefer_local else item.local, item.provider, item.model))
        return candidates[0] if candidates else None

    def fanout(
        self,
        prompt: str,
        *,
        max_agents: int = 0,
        system: str = "You are a coding assistant.",
        mode: str = "plan",
        verified_only: bool = True,
    ) -> List[Dict[str, Any]]:
        candidates = [endpoint for endpoint in self.free_first(verified_only=verified_only) if endpoint.free]
        if max_agents > 0:
            candidates = candidates[:max_agents]
        if not candidates:
            return []
        workers = min(len(candidates), max(1, int(os.getenv("OPENCLAW_MAX_PARALLEL_AGENTS", "8"))))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="openclaw-model") as pool:
            future_map = {
                pool.submit(self.chat, endpoint, prompt, system=system, mode=mode): endpoint.endpoint_id
                for endpoint in candidates
            }
            results = [future.result() for future in concurrent.futures.as_completed(future_map)]
        return sorted(results, key=lambda item: (item.get("status") != "completed", item.get("latency_ms", 0)))


__all__ = ["KILO_GATEWAY", "ModelEndpoint", "ModelFabric"]
