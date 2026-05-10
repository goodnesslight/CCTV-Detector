# 04. Моделі штучного інтелекту

Цей розділ описує всі ШІ-компоненти системи: що це, звідки взято, як працює,
де використовується, ліцензія.

## 4.1. Огляд

```
┌─────────────────────────────────────────────────────────────────┐
│                       ВХІДНИЙ ВІДЕОПОТІК                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌───────────┬───────────┬───────────────────┐
        │           │           │                   │
        ▼           ▼           ▼                   ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐         ┌─────────┐
   │ YOLO11n │ │  YuNet  │ │  SFace  │         │ByteTrack│
   │  люди   │ │  лиця   │ │  embed  │         │ трекінг │
   └─────────┘ └─────────┘ └─────────┘         └─────────┘
        │           │           │                   │
        │           └─────┬─────┘                   │
        │                 │                         │
        │           cosine match                    │
        │           з whitelist                     │
        │                 │                         │
        ▼                 ▼                         ▼
   person bbox     known/unknown_face       track_id для людей
                                                   │
                                                   ▼
                                            loitering rule
```

| Модель | Тип | Звідки | Що робить |
|--------|-----|--------|-----------|
| **YOLO11n** | Object detection (CNN) | Ultralytics | Знаходить людей у кадрі |
| **YuNet** | Face detection (CNN) | OpenCV Zoo | Знаходить обличчя у кадрі |
| **SFace** | Face recognition (CNN) | OpenCV Zoo | Кодує обличчя в 128D-вектор |
| **ByteTrack** | Multi-object tracking | supervision | Присвоює стабільний ID кожній людині між кадрами |

## 4.2. YOLO11n — детекція людей

### 4.2.1. Що це

**YOLO** = «You Only Look Once» — родина сімейств моделей реального часу для
object detection, створена Joseph Redmon (v1–v3) і потім продовжена різними
авторами / компаніями. Версія, яку використовуємо — **YOLO11**, випущена
**Ultralytics** у 2024 р.

«n» (nano) — найменша конфігурація:
- ~2.6 млн параметрів,
- 5.1 MB ваг,
- швидкість ~12 ms / кадр на RTX 3060,
- mAP50-95 на COCO ≈ 39.5%.

### 4.2.2. Архітектура

YOLO11 — це one-stage детектор з backbone'ом `C3k2` (модернізованим C3 блоком),
neck'ом на основі PAN (Path Aggregation Network) та трьома detection-головами
для multi-scale predictions. На відміну від попередніх версій, YOLO11 повністю
**anchor-free**: head'и передбачають центр об'єкта, ширину, висоту і клас
безпосередньо.

```
Input 640×640
    │
    ▼
Backbone (C3k2 blocks) ── extract features
    │
    ▼
Neck (PAN) ── multi-scale fusion
    │
    ▼
Heads (P3, P4, P5) ── predictions on 3 scales
    │
    ▼
NMS ── remove overlapping boxes
    │
    ▼
list[bbox + class + confidence]
```

### 4.2.3. Тренування і ваги

Ваги взяті з офіційного репозиторію Ultralytics, тренувалися на **COCO 2017** —
датасет з 118 000 розмічених фотографій, 80 класів. Ми використовуємо лише
**class_id=0 ("person")**:

```python
results = self._model.predict(
    frame.image,
    classes=[PERSON_CLASS_ID],  # 0 = person
    conf=self._conf,
    device=self._device,
    verbose=False,
)
```

(`app/detectors/person_detector.py`)

### 4.2.4. Звідки і ліцензія

- **Репозиторій:** https://github.com/ultralytics/ultralytics
- **Ліцензія ваг і коду:** AGPL-3.0
- **Використання у проекті:** дипломна (некомерційна) робота — задовольняє
  умови AGPL.

## 4.3. YuNet — детекція облич

### 4.3.1. Що це

**YuNet** — швидкий face-детектор, розроблений лабораторією Шеньчженського
університету (Шицюй Ву та ін., 2018; реліз для OpenCV — 2022). Поширюється
у складі **OpenCV Zoo** як готова ONNX-модель.

Особливості:
- Дуже легка: ~232 KB ваг.
- Запускається через `cv2.FaceDetectorYN` — інтерфейс OpenCV без потреби
  у власному ONNX-runtime.
- Дає не тільки bbox, а й 5 ключових точок обличчя (очі, ніс, кутики рота).

### 4.3.2. Архітектура

YuNet — це SSD-подібна архітектура з MobileNet-backbone'ом, оптимізована для
ARM/x86. Output:
```
[x, y, w, h, x1, y1, x2, y2, x3, y3, x4, y4, x5, y5, score]
 │  │  │  │  └────────── 5 face landmarks ───────────┘ │
 │  │  │  │                                            │
 └─bbox─┘                                       confidence
```

Ці 5 landmarks потім використовує SFace для **alignCrop** — перш ніж кодувати
обличчя в embedding, OpenCV вирівнює його за орієнтирами (5-point alignment).

### 4.3.3. Тренування і ваги

Тренована на **WIDER Face** — стандартний датасет для face detection (~32 000
фото). Файл моделі: `face_detection_yunet_2023mar.onnx`.

### 4.3.4. Звідки і ліцензія

- **Репозиторій моделі:** https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
- **Стаття:** Wu et al., «Efficient Face Detection: A Survey», 2022
- **Ліцензія:** Apache 2.0 (вільне використання, включно з комерційним).
- **Завантаження:** автоматично у `data/models/` при першому запуску
  (з GitHub raw, без додаткових пакетів).

## 4.4. SFace — розпізнавання облич

### 4.4.1. Що це

**SFace** — face-recognition модель (Zhong et al., 2021). Перетворює
**вирівняне обличчя** на **128-вимірний нормалізований вектор** (embedding),
який потім порівнюється з еталонами через cosine similarity.

### 4.4.2. Як використовуємо

```
вирівняне обличчя 112×112  ─►  SFace CNN  ─►  128-D вектор (нормалізований)
                                                      │
                                                      ▼
                                           cosine(emb, known_embs[name])
                                                      │
                                                      ▼
                                             max → best_name, best_sim
                                                      │
                                                      ▼
                                       best_sim ≥ 0.4 → known_face
                                       інакше         → unknown_face
```

(`app/detectors/face_recognizer.py`)

### 4.4.3. Тренування і ваги

Тренована на **MS-Celeb-1M** (10M фото, 100K людей) з ArcFace-loss.

- Файл: `face_recognition_sface_2021dec.onnx` (~38 MB)
- Точність на LFW (Labeled Faces in the Wild): ~99.6%

### 4.4.4. Поріг і дебаунс

Cosine similarity у нас порогом **0.40** за замовчуванням (налаштовується в UI).
Це консервативний поріг — вище = більше пропусків, нижче = більше FP.

Додатково: `UnknownFaceRule` має temporal smoothing (6 з 10 останніх кадрів),
щоб погасити флікер на вході в кадр (див. [06-algorithms.md](06-algorithms.md)).

### 4.4.5. Звідки і ліцензія

- **Стаття:** Zhong & Deng, «SFace: Sigmoid-Constrained Hypersphere Loss for
  Robust Face Recognition», IEEE TIP 2021.
- **Репозиторій моделі:** https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface
- **Ліцензія:** Apache 2.0.

## 4.5. ByteTrack — трекінг

### 4.5.1. Що це

**ByteTrack** (Zhang et al., ECCV 2022) — multi-object tracker, що тримає
консистентний `track_id` для кожного об'єкта між кадрами. Працює як SOTA на
MOT17/MOT20 на момент випуску.

### 4.5.2. Як працює (спрощено)

ByteTrack — **tracking-by-detection**, він не має власного детектора, а
працює з вихідними детекціями YOLO:

```
кадр t-1 → детекції → треки {1: бокс1, 2: бокс2, 3: бокс3}
кадр  t  → детекції → ?
                       │
                       ▼
        Kalman filter  ── прогноз позицій треків
                       │
                       ▼
        IoU + Hungarian ── асоціація детекцій із треками
                       │
                       ▼
        треки {1: новий бокс1, 2: новий бокс2, 3: новий бокс3, 4: NEW}
```

Ноу-хау ByteTrack: на відміну від попередніх трекерів, він використовує **і
низько-confidence детекції** для заповнення розривів (коли об'єкт на мить
закрився). Це дає стабільніші track_id у складних умовах.

### 4.5.3. Інтеграція

Через бібліотеку `supervision` (Roboflow):

```python
import supervision as sv
self._tracker = sv.ByteTrack()
tracked = self._tracker.update_with_detections(sv_dets)
```

Ми викликаємо ByteTrack тільки для людей (`label == "person"`), тому що:
- Loitering має сенс лише для людей.
- Обличчя ловляться іншою моделлю; track_id для них окремо не потрібен.

(`app/detectors/tracker.py`)

### 4.5.4. Звідки і ліцензія

- **Стаття:** https://arxiv.org/abs/2110.06864
- **Реалізація:** через `supervision` (https://github.com/roboflow/supervision)
- **Ліцензія:** MIT.

## 4.6. Інтеграція моделей у pipeline

```
                ┌──────────────────────────────────────────────┐
                │             DetectionPipeline                │
                ├──────────────────────────────────────────────┤
                │                                              │
   Frame ───►   │  for d in detectors:                         │
                │      detections.extend(d.detect(frame))      │
                │                                              │
                │  if tracker: tracker.update(detections)      │
                │                                              │
                │  for det in detections:                      │
                │      for zone in zones:                      │
                │          if zone.contains(det.bottom_center):│
                │              det.zone_name = zone.name       │
                │                                              │
                │  return ProcessingResult(detections, image)  │
                │                                              │
                └──────────────────────────────────────────────┘
```

Будь-який `detector` має імплементувати `Protocol`:

```python
@runtime_checkable
class Detector(Protocol):
    def detect(self, frame: Frame) -> list[Detection]: ...
```

Це дозволяє додавати нові моделі (детектор предметів, поведінкові класифікатори)
без змін у pipeline — лише новий клас, що поверне `list[Detection]`.

## 4.7. Чому саме ці моделі — обґрунтування

| Завдання | Чому ці моделі |
|----------|----------------|
| Детекція людей | YOLO — стандарт індустрії; YOLO11n — найновіший стабільний реліз; розмір nano для CPU-fallback. |
| Детекція облич | YuNet — лідер benchmark'у WIDER Face серед моделей < 1 MB; нативно у OpenCV без додаткових залежностей. |
| Розпізнавання облич | SFace дає 99.6% LFW при 38 MB; альтернатива (InsightFace) краща, але на Python 3.12 не збиралась з пакетів. |
| Трекінг | ByteTrack — SOTA на MOT, простий API через supervision. |

## 4.8. Що НЕ використовуємо і чому

- **InsightFace** (RetinaFace + ArcFace) — точніший за YuNet+SFace на ~1–2%, але
  у 2025 році збирання `insightface` під Python 3.12 + Windows + Visual Studio
  було проблемним, OpenCV-варіант — drop-in заміна без втрат якості для домашніх
  сценаріїв.
- **DeepStack** — окремий сервер-фасад на ML; додає мережеву затримку, нам не
  потрібен.
- **Faster R-CNN** для детекції людей — точніший, але повільніший (10× slower);
  для real-time не годиться.
- **Кастомні моделі для детекції зброї** — пробували в експерименті, не дали
  стабільної якості без значних інвестицій у датасет (див.
  [10-implementation-notes.md](10-implementation-notes.md), розділ
  «Експеримент з weapon-детектором»).
