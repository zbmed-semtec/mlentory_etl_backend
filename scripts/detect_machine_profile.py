#!/usr/bin/env python3
"""
detect_machine_profile.py

Detects GPU name/count/VRAM via nvidia-smi, matches against the
`profiles` in LLM_config_based_on_machine.yaml, and writes/updates
the matched profile's `llm` variables into an .env file.

Usage:
    python3 detect_machine_profile.py \
        --config LLM_config_based_on_machine.yaml \
        --out .env \
        [--profile default]   # skip GPU detection and use this profile
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


def all_profiles(config):
    profiles = {name: profile["llm"] for name, profile in config["profiles"].items()}
    if "default" in config:
        profiles["default"] = config["default"]["llm"]
    return profiles


def check_same_keys(profiles):
    """Every profile must define every key, otherwise switching profiles leaves stale values in .env."""
    all_keys = set().union(*(p.keys() for p in profiles.values()))
    problems = [f"{name}: missing {sorted(all_keys - p.keys())}" for name, p in profiles.items() if all_keys - p.keys()]
    if problems:
        sys.exit("ERROR: profiles must define the same keys:\n  " + "\n  ".join(problems))


def check_pinned_images(profiles):
    """vLLM images must be pinned to a version tag, `latest` silently changes the server."""
    unpinned = [f"{name}: {p['image']}" for name, p in profiles.items()
                if ":" not in p["image"] or p["image"].endswith(":latest")]
    if unpinned:
        sys.exit("ERROR: pin the vLLM image to a version tag:\n  " + "\n  ".join(unpinned))


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
    parser.add_argument("--profile", help="use this profile instead of detecting the GPUs")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text())
    profiles = all_profiles(config)
    check_same_keys(profiles)
    check_pinned_images(profiles)

    if args.profile:
        if args.profile not in profiles:
            sys.exit(f"ERROR: unknown profile '{args.profile}'. Available: {list(profiles)}")
        profile_name, llm_config = args.profile, profiles[args.profile]
    else:
        gpus = get_gpus()
        profile_name, llm_config = match_profile(gpus, config)
        if llm_config is None:
            sys.exit(f"ERROR: no matching profile (and no default) for detected GPUs: {gpus}")

    llm_config = dict(llm_config)  # copy so we don't mutate the loaded yaml
    enable_prefix_caching = llm_config.pop("enable_prefix_caching", None)
    extra_args = llm_config.pop("extra_args", "").strip()

    updates = {"MACHINE_PROFILE": profile_name}
    updates.update({k.upper(): v for k, v in llm_config.items()})

    # always explicit: newer vLLM enables prefix caching by default, and compose falls back to enabling it
    parts = ["--enable-prefix-caching" if enable_prefix_caching else "--no-enable-prefix-caching"]
    # kept in updates too: the extractor only sends request priorities when the server accepts them
    if llm_config.get("priority_scheduling") is True:
        parts.append("--scheduling-policy priority")
    if extra_args:
        parts.append(extra_args)
    updates["EXTRA_VLLM_ARGS"] = " ".join(parts)

    update_env_file(args.out, updates)

    print(f"Matched profile '{profile_name}' -> updated {args.out}")


if __name__ == "__main__":
    main()