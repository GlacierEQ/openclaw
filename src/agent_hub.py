#!/usr/bin/env python3
"""OpenClaw Free Tier Agent Hub — Heavy-duty local + cloud AI agents."""

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
    LOCAL = "local"
    FREEMIUM = "freemium"


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
    """Heavy-duty agent hub for token-heavy queries."""

    def __init__(self, config_path: str = ".openclaw/agents_config.json"):
        self.config_path = Path(config_path)
        self.agents: Dict[str, AgentConfig] = {}
        self.test_results: Dict[str, Dict] = {}
        self._load_default_agents()

    def _load_default_agents(self):
        """Load all known free tier agents — LOCAL FIRST for heavy tokens."""
        self.agents = {
            # ================================================================
            # GLACIEREQ CUSTOM MODELS (Priority - Heavy Duty)
            # ================================================================
            "omni-agent": AgentConfig(
                name="Omni-Agent",
                tier=AgentTier.LOCAL,
                provider="glaciereq",
                model="omni-agent:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "all-purpose", "glaciereq"],
            ),
            "megamind": AgentConfig(
                name="MegaMind",
                tier=AgentTier.LOCAL,
                provider="glaciereq",
                model="megamind:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "reasoning", "strategy", "glaciereq"],
            ),
            "stealth-claw": AgentConfig(
                name="Stealth-Claw",
                tier=AgentTier.LOCAL,
                provider="glaciereq",
                model="stealth-claw:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "precision", "security", "glaciereq"],
            ),
            "stealth-microwave": AgentConfig(
                name="Stealth-Microwave",
                tier=AgentTier.LOCAL,
                provider="glaciereq",
                model="stealth-microwave:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "optimization", "glaciereq"],
            ),

            # ================================================================
            # STEALTH SERIES (Local - Unlimited)
            # ================================================================
            "stealth-team": AgentConfig(
                name="Stealth Team",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-team:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "team"],
            ),
            "stealth-supernova": AgentConfig(
                name="Stealth Supernova",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-supernova:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "intelligence"],
            ),
            "stealth-sonic": AgentConfig(
                name="Stealth Sonic",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-sonic:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "speed"],
            ),
            "stealth-sherlock": AgentConfig(
                name="Stealth Sherlock",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-sherlock:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "investigation"],
            ),
            "stealth-viper": AgentConfig(
                name="Stealth Viper",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-viper:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "precision"],
            ),
            "stealth-polaris": AgentConfig(
                name="Stealth Polaris",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-polaris:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "navigation"],
            ),
            "stealth-specter": AgentConfig(
                name="Stealth Specter",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="stealth-specter:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "heavy", "unlimited", "stealth"],
            ),

            # ================================================================
            # BASE MODELS (Local - Lightweight)
            # ================================================================
            "llama3.2-1b": AgentConfig(
                name="Llama 3.2 1B",
                tier=AgentTier.LOCAL,
                provider="ollama",
                model="llama3.2:1b",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "lightweight", "fast"],
            ),

            # ================================================================
            # GROQ (Fast but limited tokens per query)
            # ================================================================
            "groq-llama3.3": AgentConfig(
                name="Groq Llama 3.3 70B",
                tier=AgentTier.FREE,
                provider="groq",
                model="llama-3.3-70b-versatile",
                endpoint="https://api.groq.com/openai/v1/chat/completions",
                api_key_env="GROQ_API_KEY",
                cost_per_1k_tokens=0.0,
                max_tokens=8192,
                capabilities=["code", "fast", "limited_tokens"],
            ),

            # ================================================================
            # OPENAI (Rate limited but powerful)
            # ================================================================
            "openai-gpt4o-mini": AgentConfig(
                name="OpenAI GPT-4o Mini",
                tier=AgentTier.FREEMIUM,
                provider="openai",
                model="gpt-4o-mini",
                endpoint="https://api.openai.com/v1/chat/completions",
                api_key_env="OPENAI_API_KEY",
                cost_per_1k_tokens=0.00015,
                max_tokens=128000,
                capabilities=["code", "reasoning", "heavy_tokens"],
            ),

            # ================================================================
            # CLINE / KILO / OPENCODE / AIDER / CONTINUE (via Groq)
            # ================================================================
            "cline-local": AgentConfig(
                name="Cline via Ollama",
                tier=AgentTier.LOCAL,
                provider="cline",
                model="stealth-team:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "agent", "browser", "unlimited"],
            ),
            "kilo-local": AgentConfig(
                name="Kilo Code via Ollama",
                tier=AgentTier.LOCAL,
                provider="kilo",
                model="stealth-team:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "agent", "orchestrator", "unlimited"],
            ),
            "opencode-local": AgentConfig(
                name="OpenCode via Ollama",
                tier=AgentTier.LOCAL,
                provider="opencode",
                model="stealth-team:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "terminal", "devops", "unlimited"],
            ),
            "aider-local": AgentConfig(
                name="Aider via Ollama",
                tier=AgentTier.LOCAL,
                provider="aider",
                model="stealth-team:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "git", "refactor", "unlimited"],
            ),
            "continue-local": AgentConfig(
                name="Continue.dev via Ollama",
                tier=AgentTier.LOCAL,
                provider="continue",
                model="stealth-team:latest",
                endpoint="http://localhost:11434/api/chat",
                api_key_env="",
                cost_per_1k_tokens=0.0,
                max_tokens=32768,
                capabilities=["code", "completion", "chat", "unlimited"],
            ),
        }

    def _post_json(self, url: str, headers: Dict, body: Dict, timeout: int = 120) -> Dict:
        headers.setdefault("User-Agent", "OpenClaw/3.1.0")
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

    def _query_ollama(self, agent: AgentConfig, prompt: str, system: str = "") -> Dict:
        """Query Ollama local model directly."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": agent.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": min(agent.max_tokens, 2048),
                "temperature": 0.3,
            }
        }

        start = time.time()
        result = self._post_json(agent.endpoint, {}, body, timeout=120)
        latency_ms = (time.time() - start) * 1000

        if "error" in result:
            return {"error": result["error"], "latency_ms": latency_ms}

        # Handle Ollama response format
        text = ""
        if isinstance(result, dict):
            msg = result.get("message", {})
            if isinstance(msg, dict):
                text = msg.get("content", "")
            text = text or result.get("response", "")

        return {
            "agent": agent.name,
            "provider": agent.provider,
            "model": agent.model,
            "response": text,
            "latency_ms": latency_ms,
            "tokens_eval": result.get("eval_count", 0) if isinstance(result, dict) else 0,
        }

    def _query_cloud(self, agent: AgentConfig, prompt: str, system: str = "") -> Dict:
        """Query cloud API."""
        api_key = os.getenv(agent.api_key_env, "") if agent.api_key_env else ""
        if not api_key:
            return {"error": f"{agent.api_key_env} not set"}

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": agent.model,
            "messages": messages,
            "max_tokens": min(agent.max_tokens, 4096),
            "temperature": 0.3,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        start = time.time()
        result = self._post_json(agent.endpoint, headers, body, timeout=60)
        latency_ms = (time.time() - start) * 1000

        if "error" in result:
            return {"error": result["error"], "latency_ms": latency_ms}

        text = ""
        if "choices" in result and result["choices"]:
            text = result["choices"][0].get("message", {}).get("content", "")

        return {
            "agent": agent.name,
            "provider": agent.provider,
            "model": agent.model,
            "response": text,
            "latency_ms": latency_ms,
        }

    def test_agent(self, agent_name: str) -> Dict:
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Agent {agent_name} not found"}

        test_prompt = "Write a Python function to check if a number is prime. Return ONLY the code."

        if agent.tier == AgentTier.LOCAL:
            result = self._query_ollama(agent, test_prompt)
        else:
            result = self._query_cloud(agent, test_prompt)

        if "error" in result:
            agent.status = "failed"
            self.test_results[agent_name] = {"status": "failed", "error": result["error"]}
        else:
            agent.status = "verified"
            self.test_results[agent_name] = {
                "status": "verified",
                "response_preview": result.get("response", "")[:200],
                "latency_ms": result.get("latency_ms", 0),
            }

        return self.test_results[agent_name]

    def test_all(self) -> Dict:
        results = {}
        for name in self.agents:
            results[name] = self.test_agent(name)
        return results

    def query(self, agent_name: str, prompt: str, system: str = "You are a coding assistant.") -> Dict:
        agent = self.agents.get(agent_name)
        if not agent:
            return {"error": f"Agent {agent_name} not found"}

        if agent.tier == AgentTier.LOCAL:
            return self._query_ollama(agent, prompt, system)
        else:
            return self._query_cloud(agent, prompt, system)

    def route_query(self, prompt: str, prefer_local: bool = True) -> Dict:
        """Route query to best available agent — GLACIEREQ FIRST for heavy tokens."""
        # Priority: GlacierEQ custom models first
        glaciereq_agents = [
            name for name, agent in self.agents.items()
            if agent.status == "verified" and agent.provider == "glaciereq"
        ]

        if glaciereq_agents:
            # Prefer omni-agent for general, megamind for reasoning, stealth-claw for code
            if any(word in prompt.lower() for word in ["think", "reason", "plan", "strategy"]):
                if "megamind" in glaciereq_agents:
                    return self.query("megamind", prompt)
            elif any(word in prompt.lower() for word in ["code", "write", "function", "class", "debug"]):
                if "stealth-claw" in glaciereq_agents:
                    return self.query("stealth-claw", prompt)
            elif any(word in prompt.lower() for word in ["optim", "fast", "speed"]):
                if "stealth-microwave" in glaciereq_agents:
                    return self.query("stealth-microwave", prompt)
            return self.query(glaciereq_agents[0], prompt)

        # Fallback to other local models
        local_agents = [
            name for name, agent in self.agents.items()
            if agent.status == "verified" and agent.tier == AgentTier.LOCAL
        ]

        if local_agents:
            return self.query(local_agents[0], prompt)

        # Fallback to cloud if no local models
        cloud_agents = [
            name for name, agent in self.agents.items()
            if agent.status == "verified" and agent.tier != AgentTier.LOCAL
        ]

        if cloud_agents:
            return self.query(cloud_agents[0], prompt)

        return {"error": "No verified agents available"}

    def get_verified_agents(self) -> List[Dict]:
        return [agent.to_dict() for agent in self.agents.values() if agent.status == "verified"]

    def get_local_agents(self) -> List[Dict]:
        return [agent.to_dict() for agent in self.agents.values() if agent.tier == AgentTier.LOCAL]

    def get_free_agents(self) -> List[Dict]:
        return [agent.to_dict() for agent in self.agents.values() if agent.tier in (AgentTier.FREE, AgentTier.LOCAL)]

    def get_report(self) -> Dict:
        return {
            "total_agents": len(self.agents),
            "verified": sum(1 for a in self.agents.values() if a.status == "verified"),
            "failed": sum(1 for a in self.agents.values() if a.status == "failed"),
            "untested": sum(1 for a in self.agents.values() if a.status == "untested"),
            "local_verified": sum(1 for a in self.agents.values() if a.status == "verified" and a.tier == AgentTier.LOCAL),
            "by_provider": {
                provider: sum(1 for a in self.agents.values() if a.provider == provider)
                for provider in set(a.provider for a in self.agents.values())
            },
        }

    def save_state(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "test_results": self.test_results,
            "report": self.get_report(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self.config_path.write_text(json.dumps(state, indent=2))


def main():
    hub = FreeTierAgentHub()

    print("=" * 70)
    print("OPENCLAW FREE TIER AGENT HUB — HEAVY DUTY")
    print("=" * 70)
    print()
    print("Testing all agents (local models handle unlimited tokens)...")
    print()

    results = hub.test_all()

    verified = 0
    failed = 0

    for name, result in results.items():
        status = result.get("status", "?")
        agent = hub.agents[name]
        tier_icon = "🏠" if agent.tier == AgentTier.LOCAL else "☁️"

        if status == "verified":
            verified += 1
            latency = result.get("latency_ms", 0)
            print(f"  ✅ {tier_icon} {name:30} | {latency:7.0f}ms | {agent.model}")
        elif status == "failed":
            failed += 1
            error = result.get("error", "?")[:40]
            print(f"  ❌ {tier_icon} {name:30} | {error}")

    print()
    print(f"Results: {verified} verified | {failed} failed")
    print()

    report = hub.get_report()
    print(f"Total: {report['total_agents']} agents")
    print(f"Local (unlimited tokens): {report['local_verified']}")
    print(f"Verified: {report['verified']}")

    hub.save_state()
    print()
    print("State saved to .openclaw/agents_config.json")

    print()
    print("=" * 70)
    print("HEAVY QUERY TEST — Local Model")
    print("=" * 70)
    print()

    result = hub.query("ollama-stealth-team", "Write a comprehensive Python class for a binary search tree with insert, delete, search, and traverse operations. Include type hints and docstrings.")
    if "response" in result:
        print(f"Agent: {result['agent']}")
        print(f"Latency: {result.get('latency_ms', 0):.0f}ms")
        print()
        print(result["response"][:1000])
    else:
        print(f"Error: {result.get('error')}")


if __name__ == "__main__":
    main()
