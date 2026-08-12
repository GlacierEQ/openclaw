#!/usr/bin/env python3
"""
APEX MASTERMIND + MEGAMIND — The Ultimate Strategic Intelligence

The brain that orchestrates everything. Combines:
- Mastermind: Autonomous orchestration, legal intelligence, fleet mastery
- MegaMind: Strategic reasoning, decision analysis, system design

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │              APEX MASTERMIND                         │
    ├─────────────────────────────────────────────────────┤
    │  CONTROL PLANE  →  Orchestration & routing           │
    │  INTELLIGENCE   →  Analysis & pattern recognition    │
    │  LEGAL GRID     →  Case management & compliance      │
    │  FLEET COMMAND  →  Deployment & automation           │
    │  MEGAMIND       →  Strategic reasoning & planning    │
    │  INFINITY       →  Simulation & projection           │
    └─────────────────────────────────────────────────────┘
"""

import json
import os
import time
import hashlib
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import uuid
from collections import defaultdict
import threading


# ============================================================================
# CORE: Mastermind Enums
# ============================================================================

class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class TaskStatus(Enum):
    """Task lifecycle status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class AgentCapability(Enum):
    """Agent capabilities."""
    ORCHESTRATION = "orchestration"
    FORENSIC = "forensic"
    LEGAL = "legal"
    PATTERN_ANALYSIS = "pattern_analysis"
    DATA_RECOVERY = "data_recovery"
    DEPLOYMENT = "deployment"
    RESEARCH = "research"
    CODE = "code"
    WRITING = "writing"
    ANALYSIS = "analysis"


class StrategicPillar(Enum):
    """Strategic pillars for decision making."""
    CONTROL = "control"
    INTELLIGENCE = "intelligence"
    LEGAL = "legal"
    FLEET = "fleet"
    MEGAMIND = "megamind"
    INFINITY = "infinity"


# ============================================================================
# CORE: Mastermind Data Structures
# ============================================================================

@dataclass
class Task:
    """A task in the mastermind system."""
    task_id: str
    title: str
    description: str
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    deadline: Optional[float] = None
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict] = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = time.time()
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Task":
        data["priority"] = TaskPriority(data["priority"])
        data["status"] = TaskStatus(data["status"])
        return cls(**data)


@dataclass
class Agent:
    """An agent in the mastermind system."""
    agent_id: str
    name: str
    capabilities: List[AgentCapability]
    status: str = "idle"
    current_task: Optional[str] = None
    max_concurrent: int = 1
    active_tasks: List[str] = field(default_factory=list)
    completed_tasks: int = 0
    success_rate: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["capabilities"] = [c.value for c in self.capabilities]
        return d
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Agent":
        data["capabilities"] = [AgentCapability(c) for c in data["capabilities"]]
        return cls(**data)
    
    def can_handle(self, capability: AgentCapability) -> bool:
        """Check if agent can handle a capability."""
        return capability in self.capabilities
    
    def is_available(self) -> bool:
        """Check if agent is available for new tasks."""
        return len(self.active_tasks) < self.max_concurrent


@dataclass
class Decision:
    """A strategic decision made by the mastermind."""
    decision_id: str
    title: str
    context: Dict[str, Any]
    options: List[Dict[str, Any]]
    recommendation: str
    confidence: float  # 0.0 to 1.0
    reasoning: str
    pillar: StrategicPillar
    timestamp: float = 0.0
    implemented: bool = False
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d["pillar"] = self.pillar.value
        return d


@dataclass
class StrategicPlan:
    """A strategic plan with multiple decisions."""
    plan_id: str
    title: str
    objective: str
    decisions: List[Decision]
    timeline: Dict[str, float]  # phase -> duration
    resources: Dict[str, Any]
    risks: List[Dict[str, Any]]
    status: str = "draft"
    created_at: float = 0.0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()


# ============================================================================
# INTELLIGENCE: MegaMind Strategic Reasoner
# ============================================================================

class MegaMindStrategic:
    """The ultimate strategic reasoning engine."""
    
    def __init__(self):
        self.decision_history: List[Decision] = []
        self.patterns: Dict[str, Any] = {}
        self.knowledge_graph: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def analyze_situation(self, context: Dict[str, Any]) -> Dict:
        """Analyze a situation and provide strategic assessment."""
        analysis = {
            "situation": context.get("description", ""),
            "factors": self._extract_factors(context),
            "risks": self._assess_risks(context),
            "opportunities": self._find_opportunities(context),
            "recommendations": [],
            "confidence": 0.0
        }
        
        # Generate recommendations
        recommendations = self._generate_recommendations(analysis)
        analysis["recommendations"] = recommendations
        
        # Calculate confidence
        analysis["confidence"] = self._calculate_confidence(analysis)
        
        return analysis
    
    def make_decision(self, title: str, context: Dict[str, Any], 
                     options: List[Dict], pillar: StrategicPillar) -> Decision:
        """Make a strategic decision."""
        # Analyze each option
        scored_options = []
        for option in options:
            score = self._score_option(option, context)
            scored_options.append({**option, "score": score})
        
        # Sort by score
        scored_options.sort(key=lambda x: x["score"], reverse=True)
        
        # Select best option
        best = scored_options[0] if scored_options else {}
        
        # Create decision
        decision = Decision(
            decision_id=str(uuid.uuid4())[:8],
            title=title,
            context=context,
            options=scored_options,
            recommendation=best.get("name", "No recommendation"),
            confidence=best.get("score", 0.0),
            reasoning=self._explain_reasoning(best, context),
            pillar=pillar
        )
        
        with self._lock:
            self.decision_history.append(decision)
        
        return decision
    
    def create_strategic_plan(self, title: str, objective: str,
                            phases: List[Dict], resources: Dict) -> StrategicPlan:
        """Create a comprehensive strategic plan."""
        decisions = []
        
        # Create decisions for each phase
        for phase in phases:
            decision = self.make_decision(
                title=f"Phase: {phase.get('name', 'Unknown')}",
                context=phase,
                options=phase.get("options", []),
                pillar=StrategicPillar.MEGAMIND
            )
            decisions.append(decision)
        
        # Create timeline
        timeline = {phase.get("name", f"phase_{i}"): phase.get("duration", 30) 
                   for i, phase in enumerate(phases)}
        
        # Assess risks
        risks = self._assess_plan_risks(phases, resources)
        
        plan = StrategicPlan(
            plan_id=str(uuid.uuid4())[:8],
            title=title,
            objective=objective,
            decisions=decisions,
            timeline=timeline,
            resources=resources,
            risks=risks
        )
        
        return plan
    
    def learn_from_outcome(self, decision: Decision, outcome: Dict):
        """Learn from decision outcomes to improve future decisions."""
        key = f"{decision.pillar.value}:{decision.title}"
        
        with self._lock:
            if key not in self.patterns:
                self.patterns[key] = {
                    "count": 0,
                    "successes": 0,
                    "avg_confidence": 0.0,
                    "factors": []
                }
            
            pattern = self.patterns[key]
            pattern["count"] += 1
            
            if outcome.get("success", False):
                pattern["successes"] += 1
            
            # Update average confidence
            pattern["avg_confidence"] = (
                (pattern["avg_confidence"] * (pattern["count"] - 1) + decision.confidence) /
                pattern["count"]
            )
            
            # Store success factors
            if outcome.get("success", False):
                pattern["factors"].extend(outcome.get("factors", []))
    
    def predict_outcome(self, context: Dict) -> Dict:
        """Predict likely outcome based on historical patterns."""
        relevant_patterns = []
        
        for key, pattern in self.patterns.items():
            if pattern["count"] > 0:
                success_rate = pattern["successes"] / pattern["count"]
                relevant_patterns.append({
                    "pattern": key,
                    "success_rate": success_rate,
                    "confidence": pattern["avg_confidence"],
                    "sample_size": pattern["count"]
                })
        
        if not relevant_patterns:
            return {"confidence": 0.5, "prediction": "insufficient_data"}
        
        # Weight by confidence and sample size
        total_weight = sum(p["confidence"] * p["sample_size"] for p in relevant_patterns)
        weighted_success = sum(
            p["success_rate"] * p["confidence"] * p["sample_size"] 
            for p in relevant_patterns
        )
        
        if total_weight > 0:
            predicted_success = weighted_success / total_weight
        else:
            predicted_success = 0.5
        
        return {
            "confidence": min(0.95, total_weight / 100),
            "predicted_success_rate": predicted_success,
            "prediction": "likely_success" if predicted_success > 0.6 else "likely_challenge",
            "patterns_applied": len(relevant_patterns)
        }
    
    def _extract_factors(self, context: Dict) -> List[Dict]:
        """Extract key factors from context."""
        factors = []
        
        # Time factors
        if "deadline" in context:
            factors.append({
                "type": "time_pressure",
                "severity": "high" if context["deadline"] - time.time() < 86400 else "medium"
            })
        
        # Resource factors
        if "resources" in context:
            resources = context["resources"]
            if resources.get("available", 0) < resources.get("required", 0):
                factors.append({
                    "type": "resource_constraint",
                    "severity": "high"
                })
        
        # Risk factors
        if "risks" in context:
            for risk in context["risks"]:
                factors.append({
                    "type": "risk",
                    "severity": risk.get("severity", "medium"),
                    "description": risk.get("description", "")
                })
        
        return factors
    
    def _assess_risks(self, context: Dict) -> List[Dict]:
        """Assess risks in the situation."""
        risks = []
        
        # Check for common risk patterns
        if context.get("complexity", 0) > 7:
            risks.append({
                "type": "complexity",
                "severity": "high",
                "description": "High complexity may cause delays"
            })
        
        if len(context.get("dependencies", [])) > 3:
            risks.append({
                "type": "dependency",
                "severity": "medium",
                "description": "Multiple dependencies increase failure risk"
            })
        
        if context.get("novelty", 0) > 0.7:
            risks.append({
                "type": "novelty",
                "severity": "medium",
                "description": "Novel approach may have unknown issues"
            })
        
        return risks
    
    def _find_opportunities(self, context: Dict) -> List[Dict]:
        """Find opportunities in the situation."""
        opportunities = []
        
        # Check for synergy opportunities
        if context.get("synergies"):
            opportunities.append({
                "type": "synergy",
                "potential": "high",
                "description": "Leverage existing synergies"
            })
        
        # Check for innovation opportunities
        if context.get("innovation_potential", 0) > 0.5:
            opportunities.append({
                "type": "innovation",
                "potential": "medium",
                "description": "Room for innovative approach"
            })
        
        return opportunities
    
    def _generate_recommendations(self, analysis: Dict) -> List[str]:
        """Generate strategic recommendations."""
        recommendations = []
        
        if analysis["risks"]:
            high_risks = [r for r in analysis["risks"] if r["severity"] == "high"]
            if high_risks:
                recommendations.append("Mitigate high-severity risks before proceeding")
        
        if analysis["opportunities"]:
            recommendations.append("Leverage identified opportunities for maximum impact")
        
        if analysis["factors"]:
            time_factors = [f for f in analysis["factors"] if f["type"] == "time_pressure"]
            if time_factors:
                recommendations.append("Consider time constraints in planning")
        
        return recommendations
    
    def _calculate_confidence(self, analysis: Dict) -> float:
        """Calculate confidence in the analysis."""
        base_confidence = 0.5
        
        # Adjust based on data quality
        if analysis["factors"]:
            base_confidence += 0.1
        
        if analysis["risks"]:
            base_confidence -= 0.1
        
        if analysis["opportunities"]:
            base_confidence += 0.1
        
        return min(0.95, max(0.1, base_confidence))
    
    def _score_option(self, option: Dict, context: Dict) -> float:
        """Score an option based on context."""
        score = 0.5  # Base score
        
        # Factor in alignment with objectives
        if option.get("aligns_with_objective", False):
            score += 0.2
        
        # Factor in resource requirements
        if option.get("resource_efficiency", 0) > 0.7:
            score += 0.1
        
        # Factor in risk level
        if option.get("risk_level", "medium") == "low":
            score += 0.1
        
        # Factor in innovation
        if option.get("innovation_score", 0) > 0.5:
            score += 0.1
        
        return min(1.0, score)
    
    def _explain_reasoning(self, best_option: Dict, context: Dict) -> str:
        """Explain the reasoning behind a recommendation."""
        reasons = []
        
        if best_option.get("score", 0) > 0.7:
            reasons.append("High alignment score")
        
        if best_option.get("aligns_with_objective"):
            reasons.append("Strongly aligned with objectives")
        
        if best_option.get("resource_efficiency", 0) > 0.7:
            reasons.append("Efficient resource usage")
        
        if best_option.get("risk_level") == "low":
            reasons.append("Low risk profile")
        
        return "; ".join(reasons) if reasons else "Based on overall assessment"


# ============================================================================
# CONTROL PLANE: Mastermind Orchestrator
# ============================================================================

class MastermindOrchestrator:
    """The central orchestration engine."""
    
    def __init__(self, node_id: str = None):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        
        # Components
        self.megamind = MegaMindStrategic()
        
        # State
        self.tasks: Dict[str, Task] = {}
        self.agents: Dict[str, Agent] = {}
        self.decisions: List[Decision] = []
        self.plans: Dict[str, StrategicPlan] = {}
        
        # Threading
        self._lock = threading.Lock()
        self._running = False
        
        # Callbacks
        self._on_task_callbacks: List[Callable] = []
        self._on_decision_callbacks: List[Callable] = []
    
    def start(self):
        """Start the mastermind."""
        self._running = True
        self._register_default_agents()
        print(f"[Mastermind] Node {self.node_id} started")
        print(f"[Mastermind] Agents: {len(self.agents)}")
        print(f"[Mastermind] MegaMind: Active")
    
    def stop(self):
        """Stop the mastermind."""
        self._running = False
        print(f"[Mastermind] Node {self.node_id} stopped")
    
    def create_task(self, title: str, description: str, 
                   priority: TaskPriority = TaskPriority.MEDIUM,
                   tags: List[str] = None) -> Task:
        """Create a new task."""
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            priority=priority,
            tags=tags or []
        )
        
        with self._lock:
            self.tasks[task.task_id] = task
        
        self._notify_task_created(task)
        return task
    
    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to an agent."""
        task = self.tasks.get(task_id)
        agent = self.agents.get(agent_id)
        
        if not task or not agent:
            return False
        
        if not agent.is_available():
            return False
        
        task.assigned_to = agent_id
        task.status = TaskStatus.ASSIGNED
        task.updated_at = time.time()
        
        agent.active_tasks.append(task_id)
        agent.current_task = task_id
        
        return True
    
    def complete_task(self, task_id: str, result: Dict) -> bool:
        """Mark a task as completed."""
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.updated_at = time.time()
        
        # Update agent
        if task.assigned_to:
            agent = self.agents.get(task.assigned_to)
            if agent:
                if task_id in agent.active_tasks:
                    agent.active_tasks.remove(task_id)
                agent.completed_tasks += 1
                agent.current_task = None
        
        return True
    
    def make_strategic_decision(self, title: str, context: Dict,
                              options: List[Dict], pillar: StrategicPillar) -> Decision:
        """Make a strategic decision using MegaMind."""
        decision = self.megamind.make_decision(title, context, options, pillar)
        
        with self._lock:
            self.decisions.append(decision)
        
        self._notify_decision_made(decision)
        return decision
    
    def create_strategic_plan(self, title: str, objective: str,
                            phases: List[Dict], resources: Dict) -> StrategicPlan:
        """Create a strategic plan."""
        plan = self.megamind.create_strategic_plan(title, objective, phases, resources)
        
        with self._lock:
            self.plans[plan.plan_id] = plan
        
        return plan
    
    def get_task_board(self) -> Dict:
        """Get current task board."""
        board = {
            "pending": [],
            "assigned": [],
            "in_progress": [],
            "review": [],
            "completed": [],
            "blocked": []
        }
        
        for task in self.tasks.values():
            status = task.status.value
            if status in board:
                board[status].append(task.to_dict())
        
        return board
    
    def get_agent_status(self) -> Dict:
        """Get status of all agents."""
        return {
            agent_id: agent.to_dict()
            for agent_id, agent in self.agents.items()
        }
    
    def get_decision_history(self) -> List[Dict]:
        """Get history of decisions."""
        return [d.to_dict() for d in self.decisions]
    
    def on_task_created(self, callback: Callable):
        """Register task creation callback."""
        self._on_task_callbacks.append(callback)
    
    def on_decision_made(self, callback: Callable):
        """Register decision callback."""
        self._on_decision_callbacks.append(callback)
    
    def _notify_task_created(self, task: Task):
        """Notify callbacks of task creation."""
        for callback in self._on_task_callbacks:
            try:
                callback(task)
            except Exception:
                pass
    
    def _notify_decision_made(self, decision: Decision):
        """Notify callbacks of decision."""
        for callback in self._on_decision_callbacks:
            try:
                callback(decision)
            except Exception:
                pass
    
    def _register_default_agents(self):
        """Register default agents."""
        default_agents = [
            Agent(
                agent_id="mastermind-primary",
                name="Mastermind Primary",
                capabilities=[AgentCapability.ORCHESTRATION, AgentCapability.ANALYSIS],
                max_concurrent=5
            ),
            Agent(
                agent_id="megamind-strategic",
                name="MegaMind Strategic",
                capabilities=[AgentCapability.ANALYSIS, AgentCapability.PATTERN_ANALYSIS],
                max_concurrent=3
            ),
            Agent(
                agent_id="forensic-specialist",
                name="Forensic Specialist",
                capabilities=[AgentCapability.FORENSIC, AgentCapability.DATA_RECOVERY],
                max_concurrent=2
            ),
            Agent(
                agent_id="legal-intelligence",
                name="Legal Intelligence",
                capabilities=[AgentCapability.LEGAL, AgentCapability.RESEARCH],
                max_concurrent=2
            ),
            Agent(
                agent_id="deployment-engine",
                name="Deployment Engine",
                capabilities=[AgentCapability.DEPLOYMENT, AgentCapability.CODE],
                max_concurrent=4
            ),
        ]
        
        for agent in default_agents:
            self.agents[agent.agent_id] = agent


# ============================================================================
# MAIN: Create Global Instance
# ============================================================================

# Global mastermind instance
_mastermind: Optional[MastermindOrchestrator] = None


def get_mastermind() -> MastermindOrchestrator:
    """Get or create the global mastermind instance."""
    global _mastermind
    if _mastermind is None:
        _mastermind = MastermindOrchestrator()
    return _mastermind


def create_mastermind(node_id: str = None) -> MastermindOrchestrator:
    """Create a new mastermind instance."""
    return MastermindOrchestrator(node_id)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="APEX Mastermind + MegaMind")
    parser.add_argument("--start", action="store_true", help="Start mastermind")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--task", help="Create a task")
    parser.add_argument("--plan", help="Create a strategic plan")
    args = parser.parse_args()
    
    mastermind = create_mastermind("kcbflux-mastermind")
    
    if args.start:
        mastermind.start()
        
        if args.task:
            task = mastermind.create_task(
                title=args.task,
                description="Created via CLI",
                priority=TaskPriority.HIGH
            )
            print(f"Task created: {task.task_id}")
        
        if args.plan:
            # Create a sample strategic plan
            phases = [
                {"name": "Phase 1: Analysis", "duration": 7, "options": [
                    {"name": "Deep analysis", "score": 0.9}
                ]},
                {"name": "Phase 2: Implementation", "duration": 14, "options": [
                    {"name": "Incremental", "score": 0.8}
                ]},
                {"name": "Phase 3: Deployment", "duration": 7, "options": [
                    {"name": "Staged rollout", "score": 0.85}
                ]}
            ]
            
            plan = mastermind.create_strategic_plan(
                title=args.plan,
                objective="Maximize system capabilities",
                phases=phases,
                resources={"time": 28, "budget": 10000}
            )
            print(f"Plan created: {plan.plan_id}")
            print(f"Phases: {len(plan.decisions)}")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            mastermind.stop()
    
    elif args.status:
        mastermind.start()
        print(json.dumps({
            "node_id": mastermind.node_id,
            "tasks": len(mastermind.tasks),
            "agents": len(mastermind.agents),
            "decisions": len(mastermind.decisions),
            "plans": len(mastermind.plans)
        }, indent=2))
