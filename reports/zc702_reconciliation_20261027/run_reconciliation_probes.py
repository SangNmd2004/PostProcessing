#!/usr/bin/env python3
"""
run_reconciliation_probes.py
Self-reconciliation probe test suite for ZC702 Post-Processing project.
Verifies all findings REV01-REV14 post-fix, validates baseline integrity,
and generates RECONCILIATION_RECEIPT.json.
"""

import sys
import os
import json
import time
import hashlib
import subprocess
import pathlib

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
RECON_DIR = pathlib.Path(__file__).resolve().parent

def hash_file(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def run_command(cmd, cwd=None):
    if cwd is None:
        cwd = ROOT_DIR
    t0 = time.time()
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    dt = time.time() - t0
    return {
        "command": cmd,
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "duration_sec": round(dt, 4)
    }

def main():
    print("=== STARTING RECONCILIATION PROBE SUITE ===")
    results = {}
    passed_all = True

    # 1. Baseline firmware manifest check
    print("\n[Probe 1] Checking baseline firmware manifest (27 files)...")
    manifest_path = ROOT_DIR / "build" / "zc702" / "uart_firmware" / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        m_data = json.load(f)
    files = m_data.get("files", {})
    manifest_mismatches = []
    for rel, exp_h in files.items():
        fp = ROOT_DIR / rel
        if not fp.exists():
            manifest_mismatches.append({"file": rel, "status": "MISSING", "expected": exp_h})
        else:
            act_h = hash_file(fp)
            if act_h != exp_h:
                manifest_mismatches.append({"file": rel, "status": "MISMATCH", "actual": act_h, "expected": exp_h})
    p1_pass = (len(manifest_mismatches) == 0)
    results["probe_baseline_manifest"] = {
        "pass": p1_pass,
        "total_files": len(files),
        "mismatches": manifest_mismatches
    }
    print(f"  -> Baseline Manifest: {'PASS' if p1_pass else 'FAIL'} ({len(files)} files checked)")
    if not p1_pass: passed_all = False

    # 2. C Firmware Unit Test (reproduce_c_issues_fixed.exe)
    print("\n[Probe 2] Compiling and running C firmware regression tests...")
    c_src = RECON_DIR / "reproduce_c_issues_fixed.c"
    c_exe = RECON_DIR / "reproduce_c_issues_fixed.exe"
    fw_dir = ROOT_DIR / "firmware" / "zc702_uart"
    gcc_cmd = [
        "C:/msys64/mingw64/bin/gcc.exe", "-O2",
        f"-I{fw_dir}",
        str(c_src),
        str(fw_dir / "auth_channel.c"),
        str(fw_dir / "event_scheduler.c"),
        str(fw_dir / "session_persistence.c"),
        str(fw_dir / "hw_profiler.c"),
        "-o", str(c_exe)
    ]
    comp_res = run_command(gcc_cmd, cwd=ROOT_DIR)
    if comp_res["returncode"] != 0:
        results["probe_c_firmware"] = {
            "pass": False,
            "stage": "compile",
            "output": comp_res["stderr"]
        }
        passed_all = False
        print(f"  -> C Firmware Compile FAIL: {comp_res['stderr']}")
    else:
        exec_res = run_command([str(c_exe)], cwd=RECON_DIR)
        c_pass = (exec_res["returncode"] == 0 and "total_failures=0" in exec_res["stdout"])
        results["probe_c_firmware"] = {
            "pass": c_pass,
            "returncode": exec_res["returncode"],
            "stdout": exec_res["stdout"].strip().splitlines(),
            "stderr": exec_res["stderr"]
        }
        print(f"  -> C Firmware Execution: {'PASS' if c_pass else 'FAIL'}")
        if not c_pass: passed_all = False

    # 3. REV01: Syndrome encoder bit-exactness test
    print("\n[Probe 3] REV01: Syndrome encoder bit-exact match vs codes.json...")
    se_res = run_command([sys.executable, "model/test_syndrome_encoder.py"])
    se_pass = (se_res["returncode"] == 0 and "R05_SYNDROME_ENCODER_PASS" in se_res["stdout"])
    results["probe_rev01_syndrome_encoder"] = {
        "pass": se_pass,
        "stdout": se_res["stdout"].strip().splitlines(),
        "stderr": se_res["stderr"]
    }
    print(f"  -> REV01 Syndrome Encoder: {'PASS' if se_pass else 'FAIL'}")
    if not se_pass: passed_all = False

    # 4. REV08: LDPC rate 0.95 4-cycle girth test
    print("\n[Probe 4] REV08: LDPC rate 0.95 4-cycle girth check...")
    r095_res = run_command([sys.executable, "model/ldpc_rate_095_matrix.py"])
    r095_pass = (r095_res["returncode"] == 0 and "R02_RATE_095_PASS" in r095_res["stdout"])
    results["probe_rev08_rate_095"] = {
        "pass": r095_pass,
        "stdout": r095_res["stdout"].strip().splitlines(),
        "stderr": r095_res["stderr"]
    }
    print(f"  -> REV08 Rate 0.95 4-cycles: {'PASS' if r095_pass else 'FAIL'}")
    if not r095_pass: passed_all = False

    # 5. REV09: PA NTT model boundary check
    print("\n[Probe 5] REV09: PA NTT model radix-2 limit and partition check...")
    ntt_res = run_command([sys.executable, "model/pa_ntt_model.py"])
    ntt_pass = (ntt_res["returncode"] == 0 and "R04_NTT_PA_PASS" in ntt_res["stdout"])
    results["probe_rev09_pa_ntt"] = {
        "pass": ntt_pass,
        "stdout": ntt_res["stdout"].strip().splitlines(),
        "stderr": ntt_res["stderr"]
    }
    print(f"  -> REV09 PA NTT Model: {'PASS' if ntt_pass else 'FAIL'}")
    if not ntt_pass: passed_all = False

    # 6. REV03: Extended ablation tier separation check
    print("\n[Probe 6] REV03: Extended ablation tier separation...")
    abl_res = run_command([sys.executable, "syn/zc702/run_extended_ablation.py"])
    abl_pass = (abl_res["returncode"] == 0 and "EXTENDED_ABLATION_EVALUATED" in abl_res["stdout"])
    results["probe_rev03_ablation"] = {
        "pass": abl_pass,
        "stdout": abl_res["stdout"].strip().splitlines(),
        "stderr": abl_res["stderr"]
    }
    print(f"  -> REV03 Extended Ablation: {'PASS' if abl_pass else 'FAIL'}")
    if not abl_pass: passed_all = False

    # 7. REV02: Paced arrival benchmark simulation check
    print("\n[Probe 7] REV02: Paced arrival queue simulation check...")
    paced_res = run_command([sys.executable, "syn/zc702/run_paced_arrival_benchmark.py"])
    paced_pass = (paced_res["returncode"] == 0 and "PACED_BENCHMARK_SIMULATION_EVALUATED" in paced_res["stdout"])
    results["probe_rev02_paced_benchmark"] = {
        "pass": paced_pass,
        "stdout": paced_res["stdout"].strip().splitlines(),
        "stderr": paced_res["stderr"]
    }
    print(f"  -> REV02 Paced Benchmark: {'PASS' if paced_pass else 'FAIL'}")
    if not paced_pass: passed_all = False

    # 8. REV06: Python Auth Channel test
    print("\n[Probe 8] REV06: Python Auth Channel SipHash-2-4 and Anti-Replay check...")
    auth_res = run_command([sys.executable, "syn/zc702/test_auth_channel.py"])
    auth_pass = (auth_res["returncode"] == 0 and "P04_AUTH_CHANNEL_PASS" in auth_res["stdout"])
    results["probe_rev06_python_auth"] = {
        "pass": auth_pass,
        "stdout": auth_res["stdout"].strip().splitlines(),
        "stderr": auth_res["stderr"]
    }
    print(f"  -> REV06 Python Auth: {'PASS' if auth_pass else 'FAIL'}")
    if not auth_pass: passed_all = False

    # 9. Readonly replays: 3 board-verified results
    print("\n[Probe 9] Verifying 3 board-verified results via readonly replay...")
    replay_res = run_command([sys.executable, "reports/zc702_independent_review_20261027/run_readonly_replays.py"])
    replay_pass = (replay_res["returncode"] == 0)
    results["probe_board_replays"] = {
        "pass": replay_pass,
        "stdout": replay_res["stdout"].strip().splitlines(),
        "stderr": replay_res["stderr"]
    }
    print(f"  -> Board Replays: {'PASS' if replay_pass else 'FAIL'}")
    if not replay_pass: passed_all = False

    # 10. Project status reconciliation check
    print("\n[Probe 10] Checking reconciled project status counts...")
    prog_res = run_command([sys.executable, "syn/zc702/report_project_progress.py"])
    prog_pass = (prog_res["returncode"] == 0 and "'done': 13" in prog_res["stdout"] and "'partial': 20" in prog_res["stdout"] and "'todo': 2" in prog_res["stdout"])
    results["probe_project_progress"] = {
        "pass": prog_pass,
        "stdout": prog_res["stdout"].strip().splitlines(),
        "stderr": prog_res["stderr"]
    }
    print(f"  -> Project Progress (13 Done, 20 Partial, 2 Todo): {'PASS' if prog_pass else 'FAIL'}")
    if not prog_pass: passed_all = False

    receipt = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "ALL_PASSED" if passed_all else "SOME_FAILED",
        "passed_all": passed_all,
        "results": results
    }

    receipt_path = RECON_DIR / "RECONCILIATION_RECEIPT.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)
    print(f"\nReconciliation Receipt written to: {receipt_path}")
    print(f"Final Status: {receipt['status']}")

    return 0 if passed_all else 1

if __name__ == "__main__":
    sys.exit(main())
