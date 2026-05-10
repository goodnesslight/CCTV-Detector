from pathlib import Path

import cv2
import numpy as np

from app.core.types import Detection


class ActivityHeatmap:
    """Накопичувальна теплова карта активності людей у кадрі.

    На кожен кадр додає внесок у grid (зменшений у `scale` разів для швидкості)
    у позиції bottom_center кожної людини, потім згладжує в часі через
    multiplicative decay. Висока активність → інтенсивніший колір на overlay.

    Persistance: grid зберігається в .npy між сесіями, щоб карта накопичувалась
    тривало. На зміну роздільної здатності — grid обнуляється."""

    def __init__(
        self,
        path: Path,
        scale: int = 4,
        decay: float = 0.998,
        splat_radius: int = 8,
        max_value: float = 5000.0,
    ) -> None:
        self._path = path
        self._scale = scale
        self._decay = decay
        self._splat_radius = splat_radius
        self._max_value = max_value
        self._grid: np.ndarray | None = None
        self._grid_shape: tuple[int, int] | None = None
        self._frames_since_save = 0
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = np.load(self._path)
            if data.ndim == 2 and data.dtype == np.float32:
                self._grid = data
                self._grid_shape = data.shape
        except Exception:
            self._grid = None

    def save(self) -> None:
        if self._grid is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            np.save(self._path, self._grid)
        except Exception:
            pass

    def reset(self) -> None:
        if self._grid is not None:
            self._grid.fill(0)
        try:
            if self._path.exists():
                self._path.unlink()
        except Exception:
            pass

    def update(self, image_shape: tuple[int, int], detections: list[Detection]) -> None:
        h, w = image_shape[:2]
        gh, gw = max(1, h // self._scale), max(1, w // self._scale)

        if self._grid is None or self._grid_shape != (gh, gw):
            self._grid = np.zeros((gh, gw), dtype=np.float32)
            self._grid_shape = (gh, gw)

        self._grid *= self._decay

        # Збираємо точки splat'у для голови. Пріоритет:
        #   1) face-детекція (known/unknown) — центр її bbox.
        #   2) person-детекція без face поряд — оцінка голови як top 15%
        #      bbox людини (там голова і для webcam, і для CCTV).
        face_points: list[tuple[int, int, tuple[int, int, int, int]]] = []
        for d in detections:
            if d.label in ("known_face", "unknown_face"):
                fx = (d.x1 + d.x2) // 2
                fy = (d.y1 + d.y2) // 2
                face_points.append((fx, fy, (d.x1, d.y1, d.x2, d.y2)))

        splat_points: list[tuple[int, int]] = [(fx, fy) for fx, fy, _ in face_points]

        for d in detections:
            if d.label != "person":
                continue
            covered_by_face = any(
                fb[0] <= ((d.x1 + d.x2) // 2) <= fb[2]
                and fb[1] <= ((d.y1 + d.y2) // 2) <= fb[3]
                for _, _, fb in face_points
            )
            # Якщо обличчя вже зафіксоване всередині цього person bbox —
            # не додаємо ще один splat для тіла, щоб не подвоювати сигнал.
            if covered_by_face:
                continue
            cx = (d.x1 + d.x2) // 2
            cy = d.y1 + int((d.y2 - d.y1) * 0.15)
            splat_points.append((cx, cy))

        r = self._splat_radius
        for px, py in splat_points:
            cx_g = px // self._scale
            cy_g = py // self._scale
            if not (0 <= cx_g < gw and 0 <= cy_g < gh):
                continue
            y0, y1 = max(0, cy_g - r), min(gh, cy_g + r + 1)
            x0, x1 = max(0, cx_g - r), min(gw, cx_g + r + 1)
            yy, xx = np.ogrid[y0:y1, x0:x1]
            dist2 = (yy - cy_g) ** 2 + (xx - cx_g) ** 2
            splat = np.exp(-dist2 / (2.0 * (r / 2) ** 2)).astype(np.float32)
            self._grid[y0:y1, x0:x1] += splat

        np.clip(self._grid, 0, self._max_value, out=self._grid)

        self._frames_since_save += 1
        if self._frames_since_save >= 300:
            self._frames_since_save = 0
            self.save()

    def overlay(self, image: np.ndarray, alpha: float = 0.55) -> np.ndarray:
        if self._grid is None:
            return image
        peak = float(self._grid.max())
        if peak < 1e-3:
            return image

        norm = (self._grid / peak * 255.0).astype(np.uint8)
        h, w = image.shape[:2]
        up = cv2.resize(norm, (w, h), interpolation=cv2.INTER_LINEAR)
        colored = cv2.applyColorMap(up, cv2.COLORMAP_JET)

        # Маска: чим інтенсивніша активність — тим більший вплив colored.
        # Низька активність (< поріг) — не перекриваємо кадр.
        mask = (up.astype(np.float32) / 255.0)[..., None] * alpha
        return (image.astype(np.float32) * (1.0 - mask) +
                colored.astype(np.float32) * mask).astype(np.uint8)
