# 06. Алгоритми обробки

## 6.1. Загальний pipeline кадру

```
┌─────────────────────────────────────────────────────────────┐
│                    DetectionPipeline.process(frame)         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │ 1. detect (паралельні детектори)│
              ├─────────────────────────────────┤
              │  if person_check:                │
              │     PersonDetector.detect(frame) │
              │  if face_check:                  │
              │     FaceRecognizer.detect(frame) │
              └─────────────────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │ 2. tracker (опціонально)        │
              ├─────────────────────────────────┤
              │  ByteTrack.update(person_dets)  │
              │  → детекції людей отримують      │
              │    track_id (стабільний між     │
              │    кадрами)                      │
              └─────────────────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │ 3. zone assignment              │
              ├─────────────────────────────────┤
              │  for det in detections:          │
              │     for zone in zones:           │
              │        if zone.contains(         │
              │           det.bottom_center):    │
              │           det.zone_name = ...    │
              │           break                  │
              └─────────────────────────────────┘
                              │
                              ▼
              ┌─────────────────────────────────┐
              │ 4. overlay rendering            │
              ├─────────────────────────────────┤
              │  draw_overlay(image,             │
              │               detections,        │
              │               zones)             │
              │  → BGR image with bboxes,        │
              │    Cyrillic labels, zone polys   │
              └─────────────────────────────────┘
                              │
                              ▼
                   ProcessingResult(detections, image)
```

## 6.2. Детекція людей (YOLO11)

### Алгоритм

1. Кадр (BGR ndarray) подається у `model.predict(image, classes=[0])`.
2. Ultralytics робить:
   - Resize до 640×640 (з padding letterbox).
   - Forward pass через CUDA-граф.
   - Decode predictions → bbox у координатах оригінального кадру.
   - NMS.
3. Фільтр за `conf >= conf_threshold` (за замовчуванням 0.4).
4. Виводимо `Detection(label="person", bbox, conf, class_id=0)`.

### Параметри (можна змінити в Settings)

- `yolo_conf_threshold` — мінімальна впевненість моделі.
  - Менше → більше FP (фантоми), більше пропусків.
  - 0.4 — баланс для звичайних кімнатних умов.

## 6.3. Розпізнавання облич (YuNet + SFace)

### Алгоритм

```
                 кадр BGR
                    │
                    ▼
           ┌──────────────────┐
           │ YuNet.detect()   │
           └──────────────────┘
                    │ список (bbox, 5 landmarks, score)
                    ▼
        ┌───────────────────────────┐
        │ для кожного обличчя:      │
        │   alignCrop(image, row)   │ ◄─ вирівнювання по 5 точках
        │     ▼                      │
        │   feature(aligned)         │ ◄─ SFace → 128-D вектор
        │     ▼                      │
        │   normalize (L2)           │
        └───────────────────────────┘
                    │ embedding e
                    ▼
        ┌───────────────────────────┐
        │ для кожного name у        │
        │ whitelist:                │
        │   max_sim = max(           │
        │     cosine(e, e_ref)       │
        │   )                        │
        │ best_name, best_sim        │
        └───────────────────────────┘
                    │
                    ▼
            ┌──────────────────┐
            │ if best_sim ≥ τ: │  → label = "known_face", person_name=best_name
            │ else:            │  → label = "unknown_face"
            └──────────────────┘
```

### Cosine similarity

Бо embedding'и нормалізовані (`||e|| = 1`), `cosine(a, b) = a · b` — простий
скалярний добуток. Діапазон [-1, +1].

```python
sim = float(np.dot(emb, known))  # face_recognizer.py: 159
```

### Поріг τ

`face_match_threshold` за замовчуванням **0.40**. Експериментально:
- 0.35 — забагато false positives (схожі люди як «знайомі»).
- 0.45 — мало пропусків при поганому ракурсі.
- 0.40 — оптимум для побутових сцен.

## 6.4. Temporal smoothing для unknown_face алерту

Це stateful-фільтр, що захищає від хибних алертів коли знайома людина на 1-3
кадрах класифікується як `unknown_face` (motion blur, поганий ракурс при появі).

### Алгоритм (в `UnknownFaceRule`)

```
Параметри:
  window     = 10   (історія 10 останніх кадрів)
  min_hits   = ≥6   (поточно — 10, потрібна повна послідовність)

Стан:
  history: deque[bool], maxlen = window

Алгоритм на кожен кадр:
  unknown = [d for d in detections if label == "unknown_face"]
  history.append(bool(unknown))

  if len(history) < window:        return []  # warmup
  if sum(history)  < min_hits:     return []  # недостатньо свідчень
  if not unknown:                  return []  # на цьому кадрі немає

  fire AlertEvent("unknown_face", …)
```

### Часова характеристика

- Window = 10 кадрів @ 30 FPS = ~333 ms.
- Реальний intruder, стабільно у кадрі → проходить.
- Знайома людина з 1-3 misclassified кадрами при поверненні → блокується.

## 6.5. Дебаунс лічильника появ персон

`SightingsTracker.on_frame()` (`app/core/sightings_tracker.py`):

```
для кожного унікального person_name у result.detections:
  if last_seen[name] не існує АБО (зараз - last_seen[name]) ≥ cooldown:
    last_seen[name] = зараз
    repo.record_sighting(name, wall_time)
```

`cooldown_seconds = 30` за замовчуванням. Логіка: якщо людина залишається
у кадрі — не накопичуємо 30+ появ за секунду; якщо вийшла та через >30 сек
повернулась — це нова поява.

Зберігається в SQLite:

```sql
CREATE TABLE person_sightings (
    name        TEXT PRIMARY KEY,
    total       INTEGER NOT NULL DEFAULT 0,
    last_seen   REAL
);

INSERT INTO person_sightings (name, total, last_seen)
VALUES (?, 1, ?)
ON CONFLICT(name) DO UPDATE SET
    total = total + 1,
    last_seen = excluded.last_seen
```

## 6.6. Зони та point-in-polygon

### Структура зони

```python
@dataclass
class Zone:
    name: str
    points: list[tuple[int, int]]
```

### Алгоритм

`zone.contains(point)`:

```python
contour = np.asarray(self.points, dtype=np.int32)
return cv2.pointPolygonTest(contour, (px, py), False) >= 0
```

`cv2.pointPolygonTest` з `measureDist=False` повертає:
- ≥ 0 — точка всередині або на границі;
- < 0 — поза.

Перевіряємо для **bottom-center** bbox'а (точка ніг людини), бо це найкраще
відображає де людина «стоїть».

### Призначення зон детекції (в `DetectionPipeline.process`)

```python
for det in detections:
    for zone in self._zones:
        if zone.contains(det.bottom_center):
            det.zone_name = zone.name
            break  # перша зона, що містить точку, виграє
```

## 6.7. Loitering — стейтова машина

Loitering = «тривале перебування людини у зоні».

### Стан правила

```python
self._tracks: dict[(track_id, zone_name), _TrackInZone]
self._last_seen: dict[(track_id, zone_name), float]

@dataclass
class _TrackInZone:
    track_id: int
    zone_name: str
    enter_ts: float
    fired: bool = False
```

### Алгоритм на кадр

```
для кожної детекції d:
   if d.label != "person" or d.track_id is None or d.zone_name is None:
       skip
   key = (d.track_id, d.zone_name)
   if key not in tracks:
       tracks[key] = _TrackInZone(enter_ts=ts)
   last_seen[key] = ts
   elapsed = ts - tracks[key].enter_ts
   if not tracks[key].fired and elapsed >= threshold:
       tracks[key].fired = True
       fire AlertEvent("loitering:<zone>", …)

# TTL cleanup:
for key, ts_last in last_seen:
   if ts - ts_last > ttl:
       del tracks[key], last_seen[key]
```

`threshold = 5.0` секунди за замовчуванням. `ttl = 2.0` сек — після такої
паузи стирання заходить в дію (особа покинула зону).

## 6.8. Pre/post буфер кліпів

`ClipManager` записує MP4-кліпи навколо моменту алерту: pre_seconds **до**
події і post_seconds **після**.

### Структура

```
┌────────────────────────────────────────────────────────┐
│  pre_buffer: deque(maxlen = pre_seconds × fps)         │
│  ─ заповнюється кадрами в реальному часі (push_frame)  │
└────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────┐
│  active_clips: list[_ActiveClip]                       │
│  ─ open VideoWriter'и, кожен пише до end_time          │
└────────────────────────────────────────────────────────┘
```

### Алгоритм

`push_frame(image, ts)`:
1. `pre_buffer.append(image)`.
2. Для кожного активного кліпа: пишемо кадр; якщо `ts >= clip.end_time` —
   закриваємо writer.

`trigger(alert_id, kind, ts, frame_size)`:
1. Створити `VideoWriter` з MP4V codec.
2. Записати **усі** кадри з `pre_buffer` (це pre-секунди).
3. Додати кліп у `active_clips` з `end_time = ts + post_seconds`.
4. Подальші кадри пишуться через `push_frame`.

### Параметри

- `clip_pre_seconds = 2.0` — 2 сек до події.
- `clip_post_seconds = 5.0` — 5 сек після події.
- `fps = 25.0` — фіксована частота для запису (не залежить від реального FPS
  потоку).

## 6.9. Cooldown алертів

`AlertManager` має кулдаун **per-kind**, щоб однотипна подія не перезаповнювала
журнал кожен кадр.

```python
last = self._last_fired.get(ev.kind, float("-inf"))
if mono - last < self._cooldown:
    continue   # пропускаємо
self._last_fired[ev.kind] = mono
fire(ev)
```

`alert_cooldown_seconds = 10.0` за замовчуванням. Тобто `unknown_face`
не вистрілить частіше за раз на 10 секунд.

`kind` зон/loitering включає назву зони, тож вторгнення в **різні** зони
не блокують одне одного:
- `kind = "zone:Серверна"`
- `kind = "zone:Каса"`
- `kind = "loitering:Каса"`

## 6.10. Privacy blur (pixelate)

`_apply_privacy_blur(image, detections)` мутує кадр: для кожного `unknown_face`
bbox робиться **down-sample → up-sample**:

```
roi = image[y1:y2, x1:x2]
small = cv2.resize(roi, (W/12, H/12), INTER_LINEAR)   # downsample
image[y1:y2, x1:x2] = cv2.resize(small, (W, H), INTER_NEAREST)  # upsample
```

Це **pixelate** — кожен квадрат 12×12 пікселів стає однорідним. Pixelate
стійкіший до reverse-обробки, ніж Gaussian blur (для нього іноді можна
відновити частину деталей через deconvolution). Для GDPR-сумісного
анонімування — стандартний підхід.

Виклик ставиться в `draw_overlay()` між zone overlay і detection rectangles —
до малювання рамок, щоб блюр не потрапив на саму рамку.

## 6.11. Теплова карта активності (heatmap)

Накопичувальний 2D-grid, що показує куди ходять люди.

### Структура

```python
class ActivityHeatmap:
    grid: np.ndarray  # shape (H/scale, W/scale), float32
    decay: float = 0.998   # multiplicative decay per frame
    splat_radius: int = 8
```

### Алгоритм на кадр

```
grid *= decay                                      # часовий розпад

для face-детекцій (known/unknown):
   splat_points.append(face_bbox_center)

для person-детекцій:
   if person вже покритий face-точкою:
       skip
   else:
       splat_points.append(top 15% bbox)           # оцінка голови

для (px, py) у splat_points:
   y_g = py / scale, x_g = px / scale
   grid[навколо (y_g, x_g)] += gaussian_splat()
```

### Чому центр голови, а не ноги

Точка ніг (`bbox.y2`) для веб-камери з фронтальним ракурсом потрапляє на
край кадру (ноги поза кадром), що деформує карту. Голова — стабільна
точка для будь-якого ракурсу.

### Overlay рендер

```
norm = grid / grid.max() * 255           # 0..255
up = cv2.resize(norm, image_shape)        # збільшити до розміру кадру
colored = cv2.applyColorMap(up, COLORMAP_JET)  # синій→зелений→жовтий→червоний
mask = up / 255 * 0.55                    # alpha залежить від інтенсивності
return image * (1-mask) + colored * mask
```

### Persistance

`grid` зберігається в `data/activity_heatmap.npy` кожні 300 кадрів та при
shutdown. Завантажується при старті. Так карта накопичується тривало,
між сесіями.

## 6.12. Snapshot capture для unknown_face алертів

При спрацюванні `unknown_face`-правила, `AlertManager._dispatch` додатково
викликає `_save_unknown_snapshot()`:

```
1. Прочитати ev.detection_bbox (x1,y1,x2,y2).
2. Розширити на 20% (для контексту — волосся, плечі).
3. Кропнути ділянку з ОРИГІНАЛЬНОГО кадру (без overlay).
4. Зберегти JPG: data/unknown_faces/<YYYYMMDD-HHMMSS>_<id8>.jpg
5. ev.snapshot_path = path → зберігається в БД при наступному repo.save(ev).
```

Знімок беремо з `result.frame.image`, а не з `result.image`, щоб не зберігати
кадр з намальованими bbox/підписами/блюром поверх обличчя.

## 6.13. Пошук по обличчю в журналі

Один з найскладніших алгоритмів — повнотекстовий пошук, але для embedding'ів.

### Етап 1 — Витягування query embedding

```
користувач завантажує фото
        │
        ▼
FaceRecognizer.embedding_for_image(path):
   img = cv2.imread(path)
   faces = YuNet.detect(img)
   beggest = argmax(faces[:, 2] * faces[:, 3])   # за площею
   aligned = SFace.alignCrop(img, faces[biggest])
   emb = SFace.feature(aligned)
   return emb / ||emb||                          # L2 normalize → 128-D unit
```

### Етап 2 — Векторизований cosine search

```
SELECT * FROM events WHERE face_embedding IS NOT NULL
        │ N рядків
        ▼
embs = np.stack([np.frombuffer(r.face_embedding, np.float32) for r in rows])
        │ shape (N, 128)
        ▼
sims = embs @ query              # batched dot product
        │ shape (N,)
        ▼
matches = [(event, float(sim)) for event, sim in zip(events, sims) if sim ≥ τ]
matches.sort(key=lambda x: x[1], reverse=True)
return matches[:200]
```

Складність: O(N × 128) операцій, де N — кількість збережених embedding'ів.
На 10K подій — ~1.3M flops, < 50 ms на сучасному CPU. NumPy робить це
в один matmul.

Поріг τ = 0.4 узгоджений з порогом класифікації `known_face`.

## 6.14. Зв'язок алгоритмів — приклад «знайома людина зайшла в зону»

```
кадр t — людина зайшла в кадр з зоною «Каса»

PersonDetector       → [bbox(person, conf=0.78)]
FaceRecognizer       → [bbox(known_face, person_name="Іван", sim=0.55)]
ByteTrack            → person.track_id = 7
zone assignment      → person.zone_name = "Каса"

DetectionPipeline    → ProcessingResult(image_with_overlay, [person, face])

AlertManager.on_frame:
  ─ UnknownFaceRule: history.append(False) → 0 unknown, no fire
  ─ ZoneIntrusionRule: fires "zone:Каса", cooldown OK
  ─ LoiteringRule: tracks[(7, "Каса")].enter_ts = ts. elapsed = 0, no fire

SightingsTracker.on_frame:
  ─ "Іван" не бачили > 30 сек → record_sighting("Іван", ts)

через 5+ сек:
  ─ LoiteringRule: tracks[(7, "Каса")].elapsed = 5.2 ≥ 5.0
  ─ FIRE "loitering:Каса"
```
