# OpenClaw — Integrity Watchdog & File System Guardian 🦅

> **Automated file integrity monitor and background watchdog daemon tracking repository state.**

[![Python](https://img.shields.io/badge/Python-3.9+-blue)]()
[![Domain](https://img.shields.io/badge/Domain-File%20Integrity-red)]()

---

## 🎯 For Recruiters & Hiring Managers

This repository implements **OpenClaw** — an integrity watchdog daemon that scans files, computes SHA-256 hashes, and detects unexpected file modifications across repository trees. It demonstrates:

- **SHA-256 hash tree construction** for cryptographic integrity verification
- **Background watchdog daemon** monitoring filesystem mutations continuously
- **Tamper detection reporting** isolating modified, added, or deleted files
- **Automated hash manifest generation** embedding security baselines in repos

**Why this matters**: Software supply chain security and system integrity require automated, continuous file auditing to catch unauthorized changes immediately.

---

## 🔬 For Engineers & Technical Reviewers

### Core Components

| Component | Language | Purpose |
|---|---|---|
| `.integrity/watchdog_daemon.py` | Python | Background daemon for continuous hash integrity auditing |
| `mastermind_sidecar.py` | Python | Mesh node registering file health with APEX Highway |

---

## 🤖 ML/AI & Programmatic Mesh Integration

- **MCP Tool**: `audit_file_integrity()` — queryable by security auditor agents
- **Mastermind Sidecar**: Primary watchdog node on APEX Highway mesh
- **SHA-256 Integrity**: Native engine driving hash manifests across 65+ repos

---

## ⚡ Quick Start

```bash
python3 .integrity/watchdog_daemon.py --check
```
