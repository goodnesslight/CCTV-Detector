# 10. Імплементаційні нотатки

Розділ збирає **технічні нюанси** реалізації — рішення, які не очевидні з коду
і які варто пам'ятати при модифікації або захисті проекту.

## 10.1. Pre-import supervision у `main.py`

**Проблема.** Ланцюжок імпортів `supervision → matplotlib → dateutil → six.moves`
використовує lazy-loader `_SixMetaPathImporter`, у якого немає атрибута `_path`.
Якщо в момент завантаження вже завантажені PySide6 (хук `shibokensupport`) і
torch (monkey-patch `inspect.getfile`), вони викликають `inspect.getsource` на
лінивому модулі `_thread` і **падають з AttributeError**.

**Рішення.**

```python
# main.py — ПЕРШІ рядки
try:
    import supervision  # noqa: F401
except ImportError:
    pass

from PySide6.QtWidgets import QApplication  # noqa: E402
```

Резолвимо ланцюжок заздалегідь, у «чистому» імпорт-контексті (поки PySide6
і torch ще не вантажились). Не міняйте порядок без розуміння.

## 10.2. Чому `cv2.putText` не використовуємо

`cv2.putText` рендерить тільки ASCII. На українському тексті виходить «?????».

**Рішення.** Усі підписи на кадрі рендеримо через PIL:

```python
img_pil = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
draw = ImageDraw.Draw(img_pil)
font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
draw.text((x, y), text, font=font, fill=(255, 255, 255))
out = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
```

Деталі — `app/core/pipeline.py`, функція `_draw_text_pil`. Шрифти, які пробуємо:

```python
_FONT_PATHS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]
```

Перший знайдений — кешується в `_FONT_CACHE`.

### Оптимізація — один прохід PIL на кадр

Замість того, щоб для кожного підпису робити окремий `Image.fromarray`/`cv2.cvtColor`
(O(N) bbox = O(N) full-image конверсій), збираємо **усі** текстові елементи в
`text_items` і робимо **одне** перетворення BGR↔RGB на кадр.

```python
def draw_overlay(image, detections, zones=None):
    out = image.copy()
    text_items = []
    if zones:
        _collect_zone_overlays(out, zones, text_items)  # cv2-малювання + збір текстів
    if detections:
        _collect_detection_overlays(out, detections, text_items)
    if text_items:
        out = _draw_text_pil(out, text_items)  # ОДНА конверсія
    return out
```

## 10.3. YuNet/SFace замість InsightFace

Початково планувалося використати **InsightFace** (RetinaFace + ArcFace) — це
SOTA для face recognition. Але:
- Збирання `insightface` під Python 3.12 + Windows + Visual Studio 2022 не
  пройшло (помилка C++ на стадії білда).
- Pre-built wheels на той момент були тільки до Python 3.10.

**Рішення:** OpenCV YuNet + SFace (готові ONNX-моделі в `cv2.FaceDetectorYN` /
`cv2.FaceRecognizerSF`). Жодних додаткових пакетів — все тягнеться з
`opencv-python`.

Точність: ~99.6% на LFW проти ~99.8% у InsightFace ArcFace. Для домашніх
сценаріїв різниця непомітна.

## 10.4. supervision (ByteTrack) — не нативна обгортка

`ByteTrack` оригінально вимагає `cython-bbox` або `lap` (linear assignment) —
ці пакети також проблемно ставляться під Windows. `supervision` від Roboflow
використовує `scipy.optimize.linear_sum_assignment` (вбудовано в scipy) — все
працює без власного компілятора.

API:

```python
import supervision as sv
tracker = sv.ByteTrack()
sv_dets = sv.Detections(xyxy=..., confidence=..., class_id=...)
tracked = tracker.update_with_detections(sv_dets)  # повертає той самий тип з tracker_id
```

Власну прив'язку `track_id` до наших `Detection` робимо через **IoU-matching**
(в `app/detectors/tracker.py`), бо ByteTrack може повернути bbox'и трохи
зміщені (через Kalman-фільтр). IoU ≥ 0.5 — порог.

## 10.5. Threading-модель PySide6

**Не використовуємо** Python `threading` — все через `QThread`.

`VideoWorker(QThread)` крутить read-loop у фоновому потоці. Передача результату
в UI — через **сигнал-слот**, що автоматично обробляє cross-thread invocation
(Qt використовує `Qt.QueuedConnection` за замовчуванням між потоками).

```python
class VideoWorker(QThread):
    result_ready = Signal(object)
    error = Signal(str)
    stream_ended = Signal()

    def run(self) -> None:
        ...
        while self._running:
            frame = self._source.read()
            ...
            self.result_ready.emit(result)  # signal у потоці
```

```python
class LiveTab(QWidget):
    def _start_source(self):
        worker = VideoWorker(...)
        worker.result_ready.connect(self._on_result)  # слот в UI-потоці
        worker.start()

    @Slot(object)
    def _on_result(self, result):
        # виконується в UI-потоці (Qt magic)
        self._camera_view.display_frame(result.image)
```

GIL не блокує паралелізм, бо тяжкі операції (cv2, torch, OpenCV) звільняють GIL.

## 10.6. Кешування шрифту PIL

Кожен виклик `ImageFont.truetype(...)` завантажує файл з диска. Без
кешування → 30 завантажень за секунду на 30 FPS = деградація.

```python
_FONT_CACHE: ImageFont.FreeTypeFont | None = None

def _get_font():
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE
    for path in _FONT_PATHS:
        try:
            _FONT_CACHE = ImageFont.truetype(path, _FONT_SIZE)
            return _FONT_CACHE
        except (OSError, IOError):
            continue
    _FONT_CACHE = ImageFont.load_default()
    return _FONT_CACHE
```

## 10.7. Експеримент із weapon-детектором (видалено)

Початково в проекті був детектор холодної зброї (ножі) на YOLO11 — як
четвертий тип детектора поряд з людьми і обличчями. Експеримент був
**свідомо вилучений** з фінальної версії.

### Що пробували

1. **COCO-fallback** (yolo11n.pt, class_id=43 «knife») — детектує тільки
   кухонні ножі на дошці, ножі у руці пропускає.
2. **Дообучення на Roboflow knife-yzefb** (~2K фото) — давав FP на руки,
   передпліччя, м'які тіні.
3. **Дообучення на ski-mask-ocnsh** для балаклав — ще гірше через мізерний
   датасет.
4. **Temporal smoothing** як архітектурна добавка (deque останніх 10 кадрів,
   потрібно 4 з 10 для проходу) — допомагає, але без якісної моделі — все
   одно на тлі базової слабкості бекенда.

### Чому видалили

- Ножі у домашніх умовах рідко з'являються — на дипломному демо буде нудно.
- Якість бекенда не дозволяла демо без feature-flickering.
- AI-частина проекту вже забезпечена YOLO + face recognition — повноцінне
  ядро без weapon-детектора.

### Що залишилось як артефакт експерименту

- Тільки в історії git — фактично в коді немає, видалено повністю
  (`app/detectors/weapon_detector.py`, `scripts/train_weapon_model.py`,
  `scripts/download_weapon_dataset.py`, поле `live_weapon_enabled`,
  правило `WeaponSightedRule`).
- `SettingsRepository.load()` фільтрує невідомі поля — старий
  `settings.json` із залишками `live_weapon_enabled` не зламає завантаження.

### Уроки експерименту

- **Якість dataset'ів public — нерівномірна.** «Knife detection» у Roboflow
  Universe має 50+ варіантів, але переважна більшість — кухонні ножі, що
  не відповідає сценарію відеоспостереження.
- **Архітектурні фільтри (temporal smoothing) — корисні, але не магія.**
  Вони компенсують 1-кадровий FP, але якщо модель стабільно бачить
  «зброю» там, де її нема — фільтр не врятує.
- **Свідоме вилучення фічі — теж результат.** Краще показати 4 функції,
  які працюють відмінно, ніж 5, де одна — постійний embarassement.

## 10.8. Sticky face identity (sticky tracking) — НЕ реалізовано

Розглянуто як можливе подальше покращення face_recognizer для випадку:
«людина не зовсім вийшла з кадру, але обличчя на 1-2 кадрах втратило
матчинг — bbox label мерехтить між ім'ям і `?`».

**Ідея:** зберігати recent (bbox, name, ts) у face_recognizer, і коли
поточне обличчя не дотягує до cosine threshold, але має IoU ≥ 0.3 з нещодавно
розпізнаним — успадковувати ім'я.

**Чому не реалізовано:** проблему «незнайоме обличчя при поверненні в кадр»
вирішено простіше — temporal smoothing на `UnknownFaceRule`. Sticky додав би
складності без видимого ефекту в типових сценаріях.

Залишається як точка розширення.

## 10.9. Dataclass-based Settings + JSON

Settings — це plain dataclass з default'ами:

```python
@dataclass
class Settings:
    yolo_conf_threshold: float = 0.4
    face_match_threshold: float = 0.4
    ...
```

Серіалізація через `dataclasses.asdict()` → `json.dumps`. Десеріалізація з
фільтрацією невідомих ключів:

```python
valid_keys = {f.name for f in fields(Settings)}
kwargs = {k: v for k, v in raw.items() if k in valid_keys}
return Settings(**kwargs)
```

Це дає простий versioning без явних схем.

## 10.10. Lazy face recognizer

`FaceRecognizer.__init__` вантажить YuNet+SFace ONNX (~38 MB) і одразу
будує whitelist (читає всі фото з `data/known_faces/`, кодує в embeddings).
Це 2-3 секунди.

Тому в `Services.face_recognizer()` він вантажиться **lazy**:
- Тільки коли користувач вмикає чекбокс «Обличчя» в Live.
- Або відкриває вкладку «Персони» і клікає «Завантажити базу облич».

Якщо людина просто хоче подивитися Live з YOLO — застосунок стартує миттєво.

## 10.11. AlertManager rule cooldown — per-kind

Ключ кулдауну — `kind` події. Структура:
- `unknown_face` — один кулдаун на тип.
- `zone:Каса` — окремий кулдаун.
- `zone:Серверна` — окремий.
- `loitering:Каса` — окремий.

Це означає: якщо в одному кадрі «вторгнення в Касу» + «вторгнення в Серверну»
— обидва спрацьовують. Якщо «Каса» спрацювало двічі за 10 сек — друге
блокується.

## 10.12. ClipManager — pre-buffer на ринг-черги

`pre_buffer = deque(maxlen = pre_seconds × fps)` — циркулярна черга, що
ХОЧ-ХОЧ-ХОЧ заповнюється кадрами. На trigger:
1. Записуємо буфер у початок MP4.
2. Подальші кадри пишемо до закінчення `post_seconds`.

Якщо `pre_seconds = 2` і `fps = 25` → maxlen = 50 кадрів. Старіші
автоматично видаляються (`deque.append` робить це O(1)).

## 10.13. SQLite schema на старті

Будь-який репозиторій (`EventsRepository`, `PersonSightingsRepository`)
викликає `_init_schema()` у конструкторі:

```python
def _init_schema(self) -> None:
    with self._connect() as conn:
        conn.executescript(_SCHEMA)
```

`CREATE TABLE IF NOT EXISTS` — ідемпотентний. Перший запуск створить таблиці,
наступні — no-op.

## 10.14. Pillow + memoryview для overlay

При роботі з кадрами 1080p (~6 MB) кожна операція `np.array` створює нову
копію. Цикл «BGR → PIL → draw → PIL → BGR» робить 3 копії. На 30 FPS це
180 MB/сек алокацій → GC pressure.

Це прийнято як технічний борг для дипломної версії. Оптимізація — TODO для
production:
- Малювати ОДНОРАЗОВО на кадр (вже зроблено через `text_items`).
- Можна використати OpenCV для текстів, попередньо рендерячи символи в
  cache як bitmap'и (як робить Frigate). Дипломна — не варто.
