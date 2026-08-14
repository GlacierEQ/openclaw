# OpenClaw Foundation Contract

This document defines the non-negotiable foundation beneath OpenClaw features.

## Canonical ownership

- `pyproject.toml` owns the packaged release version.
- `src/version.py` exposes the runtime version and must match the package release.
- `OPENCLAW_CONFIG.json` is the checked-in default policy and control-plane configuration.
- `src/openclaw.py` owns governed action execution.
- `src/audit_ledger.py` owns action provenance and chain verification.
- `src/integrity.py` owns file-integrity state and event generation.
- `src/model_fabric.py` owns model endpoint discovery and HTTP execution.
- `src/agent_runtime.py` owns model-fabric routing and observation state.
- `src/mesh_runtime.py` is the only mesh implementation. `src/mesh_intelligence.py` is compatibility exports only.

## Foundation invariants

1. **Truth before claims.** Execution, connectivity, deployment, model availability, and host capability are reported only when observed.
2. **Fail closed.** Missing execution backends and missing mutation credentials do not become success states.
3. **One implementation per responsibility.** Compatibility modules re-export canonical implementations instead of carrying forks.
4. **Host state stays host-local.** Audit logs, watchdog state, agent observations, mesh state, screenshots, and generated baselines are never source artifacts.
5. **Secure defaults.** REST and MCP bind to loopback and require bearer authentication by default.
6. **Free-first is not fake-first.** Model routes exist only when discovered or explicitly configured. Product names are never aliases for unrelated backends.
7. **Version drift is a build failure.** Package, runtime, and canonical configuration versions must agree.
8. **Every merge proves the foundation.** Compile, foundation invariants, tests, deterministic runtime proof, dependency consistency, and Docker build must pass.
9. **No receipt inflation.** A successful Docker build is packaging proof, not a live deployment receipt. A deterministic backend is test proof, not a host execution receipt.
10. **Compatibility has a size ceiling.** Legacy import paths may remain, but substantial legacy implementations may not coexist with canonical runtime modules.

## CI authority

`scripts/foundation_check.py` is the machine-enforced version of these invariants. A change that intentionally modifies a foundation invariant must update this contract, its tests, and the checker in the same pull request.

## Extension rule

New providers, agents, backends, transports, and interfaces must plug into existing contracts. They do not get parallel policy engines, alternate audit ledgers, duplicate mesh implementations, or private definitions of success.
