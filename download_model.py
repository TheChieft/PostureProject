"""
download_model.py
-----------------
Downloads the MediaPipe Pose Landmarker Lite model required by pose.py.
Run this once before starting the application.

Usage:
    python download_model.py
"""

import urllib.request
from pathlib import Path

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/latest/"
    "pose_landmarker_lite.task"
)
MODEL_PATH = Path(__file__).parent / "pose_landmarker_lite.task"


def main():
    if MODEL_PATH.exists():
        print(f"Model already present: {MODEL_PATH}")
        return

    print(f"Downloading pose model to {MODEL_PATH} ...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
