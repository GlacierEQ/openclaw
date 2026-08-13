#!/usr/bin/env python3
"""Deterministic OpenClaw runtime proof.

This proves the shipped control path, not a production desktop/browser host.
"""
from __future__ import annotations
import json, tempfile, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.action_runtime import BackendResult, NullBackend
from src.integrity import WatchdogDaemon
from src.openclaw import OpenClawEngine

class ProofBackend:
    name="deterministic-proof-backend"
    def available(self): return True
    def supports(self,action_type): return action_type in {"click","vision_sample"}
    def execute(self,action_type,target,parameters,coords): return BackendResult(True,True,self.name,"EXECUTED",{"proof":True,"action_type":action_type})

def run()->dict:
    with tempfile.TemporaryDirectory(prefix="openclaw-proof-") as tmp:
        root=Path(tmp); watched=root/"watched"; watched.mkdir(); sample=watched/"sample.txt"; sample.write_text("alpha")
        daemon=WatchdogDaemon([str(watched)],state_file=str(root/"state.json"),event_log=str(root/"integrity.jsonl")); initial=daemon.initial_scan(); sample.write_text("beta"); changed=daemon.check_integrity()
        engine=OpenClawEngine(backend=ProofBackend(),audit_file=str(root/"actions.jsonl")); denied=engine.execute_action("kernel_override","system"); executed=engine.execute_action("click","button.submit",{},(10,20),idempotency_key="proof-1"); replay=engine.execute_action("click","button.submit",{},(10,20),idempotency_key="proof-1"); audit_check=engine.verify_audit_trail()
        fail_closed=OpenClawEngine(backend=NullBackend(),audit_file=str(root/"failclosed.jsonl")).execute_action("click","button.submit",{},(10,20))
        host_health=OpenClawEngine(audit_file=str(root/"host.jsonl")).health()
        checks={"integrity_initial_scan":initial.get("status")=="SCAN_COMPLETE" and initial.get("total_files",0)==1,"integrity_detects_change":changed.get("changes")==1 and changed["events"][0]["event_type"]=="MODIFIED","policy_denies_unknown":denied.get("status")=="DENIED_BY_AKOS_POLICY","backend_receipt_executes":executed.get("status")=="OPENCLAW_ACTION_EXECUTED" and executed.get("executed") is True,"idempotency_replays_without_execution":replay.get("status")=="OPENCLAW_ACTION_REPLAYED" and replay.get("executed") is False,"audit_chain_verifies":audit_check.get("ok") is True,"missing_backend_fails_closed":fail_closed.get("status")=="OPENCLAW_BACKEND_UNAVAILABLE" and fail_closed.get("executed") is False}
        return {"schema":"openclaw.operability-proof.v2","ok":all(checks.values()),"checks":checks,"production_host":{"backend":host_health.get("backend"),"backend_available":host_health.get("backend_available"),"claim":"HOST_BACKEND_OBSERVED_ONLY"}}

def main()->int:
    result=run(); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
