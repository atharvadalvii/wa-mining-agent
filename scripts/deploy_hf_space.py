"""Publishes the app as a free Hugging Face Space (Docker SDK).

    pip install -e ".[hf]"
    huggingface-cli login
    export OPENAI_API_KEY=sk-...           # only read from your environment, never stored in a file
    python scripts/deploy_hf_space.py YOUR_HF_USERNAME/wa-mining-agent YOUR_HF_USERNAME/wa-street-data

Creates the Space if needed, sets its variables and (if OPENAI_API_KEY is in your
environment) its secret, then uploads just the files needed to build the container. The
GitHub repo stays the source of truth; re-run this to publish a new version.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["Dockerfile", "pyproject.toml", "src", "docker"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info")


def stage(dest: Path) -> list[str]:
    for name in INCLUDE:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=IGNORE)
        else:
            shutil.copy2(src, dest / name)
    # The Space's own README carries the Hugging Face config header.
    shutil.copy2(ROOT / "huggingface" / "README.md", dest / "README.md")
    return sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("space_id", help="e.g. yourname/wa-mining-agent")
    parser.add_argument("data_repo", help="dataset repo from upload_street_data_hf.py")
    parser.add_argument("--max-session-messages", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="show the files that would be uploaded")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        files = stage(Path(tmp))
        print(f"{len(files)} files staged for {args.space_id}")
        if args.dry_run:
            print("\n".join("  " + f for f in files))
            return 0

        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(args.space_id, repo_type="space", space_sdk="docker", exist_ok=True)
        api.add_space_variable(args.space_id, "GEOAGENT_DATA_HF_REPO", args.data_repo)
        api.add_space_variable(
            args.space_id, "GEOAGENT_MAX_SESSION_MESSAGES", str(args.max_session_messages)
        )
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            api.add_space_secret(args.space_id, "OPENAI_API_KEY", key)
            print("OPENAI_API_KEY set as a Space secret")
        else:
            print("OPENAI_API_KEY not in your environment: add it under the Space's Settings > Secrets")
        api.upload_folder(folder_path=tmp, repo_id=args.space_id, repo_type="space")
    print(f"published: https://huggingface.co/spaces/{args.space_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
