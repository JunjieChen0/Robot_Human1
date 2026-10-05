"""下载并解压 UCI 544 肥胖等级数据集。"""

from __future__ import annotations

import argparse
import time
import urllib.request
import zipfile
from pathlib import Path

from src.config import DATA_URL, RAW_CSV, RAW_DIR


def dataset_is_ready(csv_path: Path = RAW_CSV) -> bool:
    return csv_path.is_file()


def download_and_extract(force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if dataset_is_ready() and not force:
        print(f"数据集已存在：{RAW_CSV}")
        return RAW_CSV

    archive_path = RAW_DIR / "uci544.zip"
    if force or not archive_path.exists() or not zipfile.is_zipfile(archive_path):
        print(f"正在下载：{DATA_URL}")
        temporary_path = archive_path.with_suffix(".part")
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                request = urllib.request.Request(
                    DATA_URL,
                    headers={"User-Agent": "WeightTrend-course-project/1.0"},
                )
                with urllib.request.urlopen(request, timeout=120) as response:
                    with temporary_path.open("wb") as output_file:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            output_file.write(chunk)
                if not zipfile.is_zipfile(temporary_path):
                    raise zipfile.BadZipFile("下载内容不是完整的 ZIP 文件。")
                temporary_path.replace(archive_path)
                break
            except Exception as exc:  # 网络连接可能被远端提前关闭，允许重试
                last_error = exc
                if temporary_path.exists():
                    temporary_path.unlink()
                if attempt < 3:
                    time.sleep(attempt)
        else:
            raise RuntimeError("数据下载失败，请检查网络或手动下载官方压缩包。") from last_error
        print(f"压缩包已保存：{archive_path}")

    print("正在解压数据集……")
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(RAW_DIR / "uci544")

    if not dataset_is_ready():
        raise FileNotFoundError("解压后没有找到预期的 CSV 文件。")
    print(f"数据集准备完成：{RAW_CSV}")
    return RAW_CSV


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 UCI 544 数据集")
    parser.add_argument("--force", action="store_true", help="重新下载并解压数据")
    args = parser.parse_args()
    download_and_extract(force=args.force)


if __name__ == "__main__":
    main()
