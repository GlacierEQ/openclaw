"""Legacy import compatibility for the OpenClaw v3.2 agent fabric."""
from .agent_runtime import RuntimeAgentHub

FreeTierAgentHub = RuntimeAgentHub

__all__ = ["FreeTierAgentHub", "RuntimeAgentHub"]
