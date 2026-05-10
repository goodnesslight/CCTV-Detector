import torch
from ultralytics import YOLO

from app.config import MODELS_DIR
from app.core.frame import Frame
from app.core.types import Detection
from app.detectors._yolo_utils import ensure_yolo_model

KNIFE_CLASS_ID = 43  # COCO

# Використовується ТІЛЬКИ коли немає дообученої моделі (fallback на yolo11n.pt + COCO).
_COCO_LABEL_BY_CLASS: dict[int, str] = {
    KNIFE_CLASS_ID: "ніж",
}

# Переклад імен класів з дообученої моделі. Якщо ім'я збігається — беремо
# переклад, інакше — оригінальне ім'я з model.names.
_CUSTOM_LABEL_TRANSLATIONS: dict[str, str] = {
    "knife": "ніж",
    "knifes": "ніж",
    "holding-knife": "ніж у руці",
    "holding_knife": "ніж у руці",
    "pistol": "пістолет",
    "handgun": "пістолет",
    "gun": "пістолет",
    "rifle": "гвинтівка",
    "weapon": "зброя",
}

CUSTOM_WEIGHTS_NAME = "weapons.pt"

# Класи дообученої моделі, які надто схильні до хибних спрацьовувань
# і фільтруються на інференсі. На поточному датасеті 'holding-knife' спрацьовує
# на порожні підняті руки без ножа (візуально модель чіпляється за жест
# "рука піднята", а не за лезо). Якщо в майбутньому переобучити на менш
# зашумленому датасеті — цей фільтр можна очистити.
_NOISY_CUSTOM_CLASSES: set[str] = {
    "holding-knife",
    "holding_knife",
    "holdingknife",
}

# Захисний фільтр: реальний ніж рідко займає > 30% кадра. Великі детекції
# часто артефакт переобучення (модель чіпляється за "контекст де зазвичай ніж"
# замість самого ножа). Краще пропустити дивний кадр, ніж сипати хибними
# сповіщеннями на половину сцени.
_MAX_WEAPON_BBOX_FRAC = 0.30


class WeaponDetector:
    """Детектор холодної зброї з авто-вибором моделі:

    1) Якщо в data/models/weapons.pt лежать **дообучені ваги** — використовує
       їх і приймає всі класи з цієї моделі (наприклад 'knife', 'pistol',
       'rifle' — що б там не було). Це режим "після fine-tune", дає
       нормальну точність для CCTV.

    2) Інакше fallback на yolo11n.pt + COCO knife (id=43). Точність обмежена,
       бо COCO містить ножі переважно в кухонних контекстах. Див.
       scripts/train_weapon_model.py — він збереже дообучені ваги в
       data/models/weapons.pt, і при наступному запуску WeaponDetector
       автоматично перемкнеться в режим (1)."""

    def __init__(
        self,
        device: str | None = None,
        conf_threshold: float = 0.25,
        strict_mode: bool = False,
    ) -> None:
        custom_path = MODELS_DIR / CUSTOM_WEIGHTS_NAME
        if custom_path.exists():
            self._using_custom = True
            self._model = YOLO(str(custom_path))
            self._class_ids: list[int] | None = None
        else:
            self._using_custom = False
            base_path = ensure_yolo_model("yolo11n.pt")
            self._model = YOLO(str(base_path))
            self._class_ids = list(_COCO_LABEL_BY_CLASS.keys())

        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._conf = conf_threshold
        self._strict_mode = bool(strict_mode)

    @property
    def device(self) -> str:
        return self._device

    @property
    def using_custom_model(self) -> bool:
        return self._using_custom

    def set_conf_threshold(self, conf: float) -> None:
        self._conf = float(conf)

    def set_strict_mode(self, value: bool) -> None:
        self._strict_mode = bool(value)

    def detect(self, frame: Frame) -> list[Detection]:
        predict_kwargs = {
            "conf": self._conf,
            "device": self._device,
            "verbose": False,
        }
        if self._class_ids is not None:
            predict_kwargs["classes"] = self._class_ids

        results = self._model.predict(frame.image, **predict_kwargs)
        h, w = frame.image.shape[:2]
        max_area = h * w * _MAX_WEAPON_BBOX_FRAC
        out: list[Detection] = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), c, k in zip(xyxy, confs, cls):
                if (
                    self._using_custom
                    and self._strict_mode
                    and self._is_noisy_class(int(k))
                ):
                    continue
                bbox_area = max(0, x2 - x1) * max(0, y2 - y1)
                if bbox_area > max_area:
                    continue
                kind = self._resolve_kind_label(int(k))
                out.append(
                    Detection(
                        x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                        label="weapon",
                        confidence=float(c),
                        class_id=int(k),
                        annotation=f"{kind} {float(c):.2f}",
                    )
                )
        return out

    def _is_noisy_class(self, class_id: int) -> bool:
        try:
            raw = str((self._model.names or {}).get(class_id, "")).lower().strip()
        except Exception:
            return False
        return raw in _NOISY_CUSTOM_CLASSES

    def _resolve_kind_label(self, class_id: int) -> str:
        if self._using_custom:
            try:
                names = self._model.names or {}
                raw = str(names.get(class_id, "оружие"))
                return _CUSTOM_LABEL_TRANSLATIONS.get(raw.lower(), raw)
            except Exception:
                return "оружие"
        return _COCO_LABEL_BY_CLASS.get(class_id, "оружие")
