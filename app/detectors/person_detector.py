import torch
from ultralytics import YOLO

from app.core.frame import Frame
from app.core.types import Detection
from app.detectors._yolo_utils import ensure_yolo_model

PERSON_CLASS_ID = 0  # COCO


class PersonDetector:
    def __init__(
        self,
        model_name: str = "yolo11n.pt",
        device: str | None = None,
        conf_threshold: float = 0.4,
    ) -> None:
        model_path = ensure_yolo_model(model_name)
        self._model = YOLO(str(model_path))
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._conf = conf_threshold

    def detect(self, frame: Frame) -> list[Detection]:
        results = self._model.predict(
            frame.image,
            classes=[PERSON_CLASS_ID],
            conf=self._conf,
            device=self._device,
            verbose=False,
        )
        out: list[Detection] = []
        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue
            xyxy = boxes.xyxy.cpu().numpy()
            conf = boxes.conf.cpu().numpy()
            cls = boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), c, k in zip(xyxy, conf, cls):
                out.append(
                    Detection(
                        x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                        label="person",
                        confidence=float(c),
                        class_id=int(k),
                    )
                )
        return out

    @property
    def device(self) -> str:
        return self._device

    def set_conf_threshold(self, conf: float) -> None:
        self._conf = float(conf)
