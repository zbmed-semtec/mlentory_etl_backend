#!/usr/bin/env python3
"""
detect_machine_profile.py

Detects GPU name/count/VRAM via nvidia-smi, matches against the
`profiles` in LLM_config_based_on_machine.yaml, and writes/updates
the matched profile's `llm` variables into an .env file.

Usage:
    python3 detect_machine_profile.py \
        --config LLM_config_based_on_machine.yaml \
        --out .env
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def get_gpus():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    gpus = []
    for line in out.splitlines():
        name, mem = [p.strip() for p in line.rsplit(",", 1)]
        gpus.append({"name": name, "vram_gb": float(mem) / 1024})
    return gpus


def match_profile(gpus, config):
    names = [g["name"].lower() for g in gpus]
    min_vram = min(g["vram_gb"] for g in gpus)
    for name, profile in config["profiles"].items():
        m = profile["match"]
        if (
            m.get("gpu_name_contains", "").lower() in " ".join(names)
            and len(gpus) >= m.get("min_gpu_count", 1)
            and min_vram >= m.get("min_vram_gb_per_gpu", 0)
        ):
            return name, profile["llm"]
    if "default" in config:
        return "default", config["default"]["llm"]
    return None, None


def format_value(v):
    s = str(v)
    if any(c in s for c in ' \t<>"\'$`#'):
        return f'"{s}"'
    return s


def update_env_file(path: Path, updates: dict):
    if path.exists():
        path.with_suffix(path.suffix + ".bak").write_text(path.read_text())
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in updates:
            lines[i] = f"{key}={format_value(updates[key])}"
            seen.add(key)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={format_value(value)}")
    path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    gpus = get_gpus()
    config = yaml.safe_load(args.config.read_text())
    profile_name, llm_config = match_profile(gpus, config)

    if llm_config is None:
        sys.exit(f"ERROR: no matching profile (and no default) for detected GPUs: {gpus}")

    updates = {"MACHINE_PROFILE": profile_name}
    updates.update({k.upper(): v for k, v in llm_config.items()})
    update_env_file(args.out, updates)

    print(f"Matched profile '{profile_name}' -> updated {args.out}")


if __name__ == "__main__":
    main()