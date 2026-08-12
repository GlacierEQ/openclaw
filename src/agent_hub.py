#!/usr/bin/env python3
"""OpenClaw Free Tier Agent Hub — Unified access to free AI coding agents."""

import hashlib
import json
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum


class AgentTier(Enum):
    FREE = "free"
    FREEMIUM = "freemium"
    LOCAL = "local"
    PAID = "paid"


@dataclass
class AgentConfig:
    name: str
    tier: AgentTier
    provider: str
    model: str
    endpoint: str
    api_key_env: str
    cost_per_1k_tokens: float
    max_tokens: int
    capabilities: List[str]
    status: str = "untested"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["tier"] = self.tier.value
        return d


class FreeTierAgentHub:
    """Unified hub for all free tier AI coding agents."""

    def __init__(self, config_path: str = ".openclaw/agents_config.json"):
        self.config_path = Path(config_path)
        self.agents: Dict[str, AgentConfig] = {}
        self.test_results: Dict[str, Dict] = {}
        self._load_default_agents()

    def _load_default_agents(self):
        """Load all known free tier agents."""
        self.agents = {
            # === GROQ (Free Tier - Fast Inference) ===
            "groq-llama3.3": AgentConfig(
                name="Groq Llama 3.3 70B",
                tier=AgentTier.FREE,
                provider="groq",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "reasoning", "analysis"],
            ),
            "groq-llama3.1": AgentConfig(
                name="Groq Llama 3.1 8B",
                tier=AgentTier.FREE,
                provider="groq",
                model="llama-3.1-8b-instant",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "fast"],
            ),
            "groq-qwen3": AgentConfig(
                name="Groq Qwen 3.6 27B",
                tier=AgentTier.FREE,
                provider="groq",
                model="qwen/qwen3.6-27b",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "reasoning"],
            ),
            "groq-allam": AgentConfig(
                name="Groq Allam 2 7B",
                tier=AgentTier.FREE,
                provider="groq",
                model="allam-2-7b",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "lightweight"],
            ),

            # === OPENAI (Free Credits) ===
            "openai-gpt4o": AgentConfig(
                name="OpenAI GPT-4o",
                tier=AgentTier.FREEMIUM,
                provider="openai",
                model="gpt-4o",
                endpoint="https://api.openai.com/v1/chat/completions",
                api_key_env="OPENAI_API_KEY",
                cost_per_1k_tokens=0.005,
                max_tokens=128000,
                capabilities=["code", "reasoning", "vision", "analysis"],
            ),
            "openai-gpt4o-mini": AgentConfig(
                name="OpenAI GPT-4o Mini",
                tier=AgentTier.FREEMIUM,
                provider="openai",
                model="gpt-4o-mini",
                endpoint="https://api.openai.com/v1/chat/completions",
                api_key_env="OPENAI_API_KEY",
                cost_per_1k_tokens=0.00015,
                max_tokens=128000,
                capabilities=["code", "reasoning"],
            ),

            # === GITHUB COPILOT (Free with GitHub Account) ===
            "github-copilot": AgentConfig(
                name="GitHub Copilot",
                tier=AgentTier.FREE,
                provider="github",
                model="gpt-4o",
                endpoint="https://api.githubcopilot.com/chat/completions",
                api_key_env="GITHUB_PRIMARY_TOKEN",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "autocomplete", "chat"],
            ),

            # === CLINE (BYOK - Use any model) ===
            "cline-groq": AgentConfig(
                name="Cline via Groq",
                tier=AgentTier.FREE,
                provider="cline",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "agent", "browser", "approval"],
            ),

            # === KILO CODE (BYOK - Roo Code Successor) ===
            "kilo-groq": AgentConfig(
                name="Kilo Code via Groq",
                tier=AgentTier.FREE,
                provider="kilo",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "agent", "orchestrator", "memory"],
            ),

            # === OPENCODE (Terminal TUI) ===
            "opencode-groq": AgentConfig(
                name="OpenCode via Groq",
                tier=AgentTier.FREE,
                provider="opencode",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "terminal", "devops"],
            ),

            # === AIDER (Terminal - Git Native) ===
            "aider-groq": AgentConfig(
                name="Aider via Groq",
                tier=AgentTier.FREE,
                provider="aider",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "git", "refactor"],
            ),

            # === CONTINUE.DEV (Open Source) ===
            "continue-groq": AgentConfig(
                name="Continue.dev via Groq",
                tier=AgentTier.FREE,
                provider="continue",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "completion", "chat", "local"],
            ),

            # === OLLAMA (100% Local) ===
            "ollama-local": AgentConfig(
                name="Ollama Local",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="codellama:13b",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=4096,
                capabilities=["code", "local", "privacy"],
            ),

            # === OPENROUTER (Free Models) ===
            "openrouter-llama3": AgentConfig(
                name="OpenRouter Llama 3",
                tier=AgentTier.FREE,
                provider="openrouter",
                model="meta-llama/llama-3.1-8b-instruct:free",
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                api_key_env="OPENROUTER_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "free"],
            ),
            "openrouter-gemma2": AgentConfig(
                name="OpenRouter Gemma 2",
                tier=AgentTier.FREE,
                provider="openrouter",
                model="google/gemma-2-9b-it:free",
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                api_key_env="OPENROUTER_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "free"],
            ),

            # === DEEPSEEK (Free Tier) ===
            "deepseek-r1": AgentConfig(
                name="DeepSeek R1",
                tier=AgentTier.FREE,
                provider="deepseek",
                model="deepseek-r1",
                endpoint="https://api.deepseek.com/v1/chat/completions",
                api_key_env="DEEPSEEK_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=65536,
                capabilities=["code", "reasoning", "chain-of-thought"],
            ),

            # === GOOGLE GEMINI (Free Tier) ===
            "gemini-flash": AgentConfig(
                name="Google Gemini Flash",
                tier=AgentTier.FREE,
                provider="gemini",
                model="gemini-2.0-flash",
                endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                api_key_env="GEMINI_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "fast", "free"],
            ),
        }

    def _post_json(self, url: str, headers: Dict, body: Dict, timeout: int = 30) -> Dict:
        # Add User-Agent to prevent 403 blocks
        headers.setdefault("User-Agent", "OpenClaw/3.0.0")
        headers.setdefault("Accept", "application/json")
        
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def test_agent(self, agent_name: str) -> Dict:
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Agent {agent_name} not found"}

        api_key = os.getenv(agent.api_key_env, "") if agent.api_key_env else ""

        if agent.tier == AgentTier.LOCAL:
            return self._test_local_agent(agent)

        if not api_key:
            return {"status": "SKIP", "reason": f"{agent.api_key_env} not set"}

        messages = [
            {"role": "system", "content": "You are a helpful coding assistant. Respond concisely."},
            {"role": "user", "content": "Write a Python function to calculate fibonacci numbers. Return ONLY the code."},
        ]

        body = {
            "model": agent.model,
            "messages": messages,
            "max_tokens": 256,
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        if agent.provider == "github":
            headers["Copilot-Integration-Id"] = "vscode-chat"

        start = time.time()
        result = self._post_json(agent.endpoint, headers, body)
        latency_ms = (time.time() - start) * 1000

        if "error" in result:
            agent.status = "failed"
            self.test_results[agent_name] = {
                "status": "failed",
                "error": result["error"],
                "latency_ms": latency_ms,
            }
        else:
            text = ""
            if "choices" in result and result["choices"]:
                text = result["choices"][0].get("message", {}).get("content", "")
            agent.status = "verified"
            self.test_results[agent_name] = {
                "status": "verified",
                "response_preview": text[:200],
                "latency_ms": latency_ms,
                "model": agent.model,
            }

        return self.test_results[agent_name]

    def _test_local_agent(self, agent: AgentConfig) -> Dict:
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                if agent.model.split(":")[0] in str(models):
                    agent.status = "verified"
                    return {"status": "verified", "available_models": models}
                else:
                    agent.status = "model_missing"
                    return {"status": "model_missing", "available_models": models}
        except Exception:
            agent.status = "offline"
            return {"status": "offline", "reason": "Ollama not running"}

    def test_all(self) -> Dict:
        results = {}
        for name in self.agents:
            results[name] = self.test_agent(name)
        return results

    def get_verified_agents(self) -> List[Dict]:
        return [
            agent.to_dict()
            for agent in self.agents.values()
            if agent.status == "verified"
        ]

    def get_free_agents(self) -> List[Dict]:
        return [
            agent.to_dict()
            for agent in self.agents.values()
            if agent.tier in (AgentTier.FREE, AgentTier.LOCAL)
        ]

    def query(self, agent_name: str, prompt: str, system: str = "You are a coding assistant.") -> Dict:
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Agent {agent_name} not found"}

        api_key = os.getenv(agent.api_key_env, "") if agent.api_key_env else ""
        if agent.tier != AgentTier.LOCAL and not api_key:
            return {"error": f"{agent.api_key_env} not set"}

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        body = {
            "model": agent.model,
            "messages": messages,
            "max_tokens": agent.max_tokens,
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        result = self._post_json(agent.endpoint, headers, body)

        if "error" in result:
            return result

        text = ""
        if "choices" in result and result["choices"]:
            text = result["choices"][0].get("message", {}).get("content", "")

        return {
            "agent": agent_name,
            "provider": agent.provider,
            "model": agent.model,
            "response": text,
        }

    def route_query(self, prompt: str, prefer_free: bool = True) -> Dict:
        """Route query to best available free agent."""
        free_agents = [
            name for name, agent in self.agents.items()
            if agent.status == "verified" and agent.tier == AgentTier.FREE
        ]

        if not free_agents:
            free_agents = [
                name for name, agent in self.agents.items()
                if agent.status == "verified"
            ]

        if not free_agents:
            return {"error": "No verified agents available"}

        # Prefer Groq for speed, then others
        priority_order = ["groq-llama3", "groq-mixtral", "github-copilot", "cline-groq"]
        for name in priority_order:
            if name in free_agents:
                return self.query(name, prompt)

        return self.query(free_agents[0], prompt)

    def save_state(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "test_results": self.test_results,
            "verified_count": sum(1 for a in self.agents.values() if a.status == "verified"),
            "total_count": len(self.agents),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.config_path.write_text(json.dumps(state, indent=2))

    def get_report(self) -> Dict:
        return {
            "total_agents": len(self.agents),
            "verified": sum(1 for a in self.agents.values() if a.status == "verified"),
            "failed": sum(1 for a in self.agents.values() if a.status == "failed"),
            "untested": sum(1 for a in self.agents.values() if a.status == "untested"),
            "by_provider": {
                provider: sum(1 for a in self.agents.values() if a.provider == provider)
                for provider in set(a.provider for a in self.agents.values())
            },
            "by_tier": {
                tier.value: sum(1 for a in self.agents.values() if a.tier == tier)
                for tier in AgentTier
            },
        }


def main():
    hub = FreeTierAgentHub()

    print("=" * 60)
    print("OPENCLAW FREE TIER AGENT HUB")
    print("=" * 60)
    print()

    print("Testing all agents...")
    print()
    results = hub.test_all()

    verified = 0
    failed = 0
    skipped = 0

    for name, result in results.items():
        status = result.get("status", "?")
        agent = hub.agents[name]
        if status == "verified":
            verified += 1
            latency = result.get("latency_ms", 0)
            print(f"  ✅ {name:25} | {agent.provider:12} | {latency:6.0f}ms | {agent.model}")
        elif status == "failed":
            failed += 1
            error = result.get("error", "?")[:50]
            print(f"  ❌ {name:25} | {agent.provider:12} | {error}")
        else:
            skipped += 1
            reason = result.get("reason", "?")[:50]
            print(f"  ⏭️  {name:25} | {agent.provider:12} | {reason}")

    print()
    print(f"Results: {verified} verified | {failed} failed | {skipped} skipped")
    print()

    report = hub.get_report()
    print(f"Total agents: {report['total_agents']}")
    print(f"By tier: {report['by_tier']}")

    hub.save_state()
    print()
    print("State saved to .openclaw/agents_config.json")


if __name__ == "__main__":
    main()
