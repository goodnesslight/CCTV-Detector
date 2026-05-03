import shutil
from pathlib import Path
from urllib.request import urlretrieve

import cv2
import numpy as np

from app.config import MODELS_DIR
from app.core.frame import Frame
from app.core.types import Detection

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _ensure_model(filename: str, url: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / filename
    if not target.exists():
        urlretrieve(url, target)
    return target


class FaceRecognizer:
    def __init__(
        self,
        known_faces_dir: Path,
        match_threshold: float = 0.4,
        det_score_threshold: float = 0.7,
    ) -> None:
        det_path = _ensure_model(YUNET_FILE, YUNET_URL)
        rec_path = _ensure_model(SFACE_FILE, SFACE_URL)

        self._detector = cv2.FaceDetectorYN.create(
            model=str(det_path),
            config="",
            input_size=(320, 320),
            score_threshold=det_score_threshold,
            nms_threshold=0.3,
            top_k=5000,
        )
        self._recognizer = cv2.FaceRecognizerSF.create(
            model=str(rec_path),
            config="",
        )

        self._dir = known_faces_dir
        self._threshold = match_threshold
        self._whitelist: dict[str, list[np.ndarray]] = {}
        self._load_whitelist()

    def _detect_raw(self, image: np.ndarray) -> np.ndarray | None:
        h, w = image.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(image)
        return faces

    def _embed(self, image: np.ndarray, face_row: np.ndarray) -> np.ndarray:
        aligned = self._recognizer.alignCrop(image, face_row)
        feat = self._recognizer.feature(aligned).flatten().astype(np.float32)
        norm = np.linalg.norm(feat)
        if norm < 1e-8:
            return feat
        return feat / norm

    def _embedding_from_path(self, image_path: Path) -> np.ndarray | None:
        img = cv2.imread(str(image_path))
        if img is None:
            return None
        faces = self._detect_raw(img)
        if faces is None or len(faces) == 0:
            return None
        # Pick the largest face (w * h)
        largest_idx = int(np.argmax(faces[:, 2] * faces[:, 3]))
        return self._embed(img, faces[largest_idx])

    def _load_whitelist(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        for person_dir in sorted(self._dir.iterdir()):
            if not person_dir.is_dir():
                continue
            name = person_dir.name
            for img_path in sorted(person_dir.iterdir()):
                if img_path.suffix.lower() not in IMAGE_EXTS:
                    continue
                emb = self._embedding_from_path(img_path)
                if emb is not None:
                    self._whitelist.setdefault(name, []).append(emb)

    def add_person(self, name: str, image_path: Path) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Имя не может быть пустым")
        if name.startswith(".") or any(c in name for c in r'\/:*?"<>|'):
            raise ValueError("Имя содержит недопустимые символы")

        target_dir = self._dir / name
        target_dir.mkdir(parents=True, exist_ok=True)

        target = target_dir / image_path.name
        i = 1
        while target.exists():
            target = target_dir / f"{image_path.stem}_{i}{image_path.suffix}"
            i += 1
        shutil.copy2(image_path, target)

        emb = self._embedding_from_path(target)
        if emb is None:
            target.unlink()
            if not any(target_dir.iterdir()):
                target_dir.rmdir()
            raise ValueError("Лицо не найдено на фото")

        self._whitelist.setdefault(name, []).append(emb)
        return len(self._whitelist[name])

    def remove_person(self, name: str) -> None:
        self._whitelist.pop(name, None)
        person_dir = self._dir / name
        if person_dir.exists():
            shutil.rmtree(person_dir)

    def list_persons(self) -> list[tuple[str, int]]:
        return [(name, len(embs)) for name, embs in sorted(self._whitelist.items())]

    def detect(self, frame: Frame) -> list[Detection]:
        faces = self._detect_raw(frame.image)
        if faces is None or len(faces) == 0:
            return []

        h, w = frame.image.shape[:2]
        out: list[Detection] = []
        for row in faces:
            x, y, fw, fh = row[:4]
            x1 = max(0, int(x))
            y1 = max(0, int(y))
            x2 = min(w, int(x + fw))
            y2 = min(h, int(y + fh))
            if x2 <= x1 or y2 <= y1:
                continue

            emb = self._embed(frame.image, row)

            best_name: str | None = None
            best_sim = -1.0
            for name, embs in self._whitelist.items():
                for known in embs:
                    sim = float(np.dot(emb, known))
                    if sim > best_sim:
                        best_sim = sim
                        best_name = name

            if best_name is not None and best_sim >= self._threshold:
                label = "known_face"
                annotation = f"{best_name} ({best_sim:.2f})"
                conf = best_sim
                cls = 1
            else:
                label = "unknown_face"
                annotation = "?"
                conf = float(row[14]) if row.shape[0] > 14 else 0.0
                cls = 2

            out.append(
                Detection(
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    label=label, confidence=float(conf), class_id=int(cls),
                    annotation=annotation,
                )
            )
        return out

    @property
    def threshold(self) -> float:
        return self._threshold

    def set_match_threshold(self, value: float) -> None:
        self._threshold = float(value)

    def set_det_threshold(self, value: float) -> None:
        try:
            self._detector.setScoreThreshold(float(value))
        except Exception:
            pass
