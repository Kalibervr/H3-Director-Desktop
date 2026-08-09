"""Run one real local MiniMax H3 render through the development provider."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.comfyui_minimax_h3_provider import (  # noqa: E402
    ComfyUIMiniMaxH3Provider,
    ProviderError,
    SingleSceneRequest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    parser.add_argument("--input-image", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--render-root", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    provider = ComfyUIMiniMaxH3Provider(
        workflow_path=REPO_ROOT / "workflows" / "minimax_h3_single_scene_api.json",
        output_root=args.output_root,
        render_root=args.render_root,
        ffprobe_path=args.ffprobe,
    )
    try:
        result = provider.render(
            base_url=args.base_url,
            request=SingleSceneRequest(prompt=args.prompt, input_image=args.input_image, seed=args.seed),
        )
    except ProviderError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    print(json.dumps({
        "status": "complete",
        "prompt_id": result.prompt_id,
        "output_file": str(result.output_file),
        "metadata_file": str(result.metadata_file),
        "ffprobe": asdict(result.video),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
