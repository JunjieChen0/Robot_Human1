"""Fetch pinned official browser assets; verify hashes before writing the local cache."""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time
import urllib.request


FRONTEND = Path(__file__).resolve().parents[1] / "src/squat_frontend"


def fetch(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "WeightTrend-squat-course/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def prepare(check_only=False):
    manifest = json.loads((FRONTEND / "asset_manifest.json").read_text(encoding="utf-8"))
    vendor = FRONTEND / "vendor"
    needed = [name for name, expected in manifest["files"].items()
              if not (vendor / name).is_file() or hashlib.sha256((vendor / name).read_bytes()).hexdigest() != expected]
    if not needed:
        print("姿态模型与浏览器资源校验通过，复用本地缓存。")
        return
    if check_only:
        raise RuntimeError("模型资源缺失或校验失败：" + ", ".join(needed))
    print("首次下载固定版本的官方模型与浏览器资源，需要联网；后续复用。")
    package_names = [name for name in needed if name != "pose_landmarker_lite.task"]
    payloads = {}
    if package_names:
        raw = fetch(manifest["package_url"])
        if base64.b64encode(hashlib.sha512(raw).digest()).decode() != manifest["package_sha512_base64"]:
            raise RuntimeError("官方npm压缩包完整性校验失败，未写入缓存。")
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for name in package_names:
                payloads[name] = archive.extractfile("package/" + name).read()
    if "pose_landmarker_lite.task" in needed:
        payloads["pose_landmarker_lite.task"] = fetch(manifest["model_url"])
    for name, raw in payloads.items():
        if hashlib.sha256(raw).hexdigest() != manifest["files"][name]:
            raise RuntimeError("资源SHA256不匹配，未写入：" + name)
    for name, raw in payloads.items():
        target = vendor / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    print("资源已下载并验证；不需要Python MediaPipe或显卡运行库。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    prepare(parser.parse_args().check_only)
