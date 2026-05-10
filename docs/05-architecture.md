# 05. Архітектура застосунку

## 5.1. Архітектурний огляд

Застосунок дотримується **layered architecture**, з чіткими шарами для різних
обов'язків. Залежності спрямовані лише «зверху-вниз»: UI → Services → Core / Detectors / Storage.

```
┌─────────────────────────────────────────────────────────────────┐
│                         UI Layer (PySide6)                      │
│   MainWindow ─ QTabWidget ─ {Live, Persons, Zones, Events,      │
│                              Statistics, Settings}              │
└────────────────────────┬────────────────────────────────────────┘
                         │  signals/slots, прямі виклики методів
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Services (composition)                    │
│   Services — single facade:                                     │
│     • settings, settings_repo                                   │
│     • person_detector(), face_recognizer() — lazy factories     │
│     • alerts: AlertManager                                      │
│     • sightings: SightingsTracker, sightings_repo               │
│     • events_repo                                               │
│     • zones(), save_zones()                                     │
│     • create_tracker() → ByteTrack                              │
└────────┬─────────────────┬─────────────────┬───────────────────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌────────────────┐ ┌───────────────┐ ┌──────────────────────────┐
│     Core       │ │   Detectors   │ │        Alerts            │
│                │ │               │ │                          │
│ • Frame        │ │ • Person      │ │ • AlertManager           │
│ • Detection    │ │   Detector    │ │ • UnknownFaceRule        │
│ • Pipeline     │ │ • Face        │ │ • ZoneIntrusionRule      │
│ • Zone         │ │   Recognizer  │ │ • LoiteringRule          │
│ • VideoSource  │ │ • ByteTrack   │ │ • ClipManager            │
│ • VideoWorker  │ │   wrapper     │ │ • SoundPlayer + TTS      │
│ • Settings     │ │               │ │                          │
│ • Sightings    │ │               │ │                          │
│   Tracker      │ │               │ │                          │
└────────────────┘ └───────────────┘ └──────────────────────────┘
                          │                       │
                          ▼                       ▼
                  ┌───────────────────────────────────────┐
                  │           Storage (SQLite + JSON)     │
                  │                                       │
                  │ • EventsRepository    (events.db)     │
                  │ • PersonSightingsRepo (events.db)     │
                  │ • SettingsRepository  (settings.json) │
                  │ • ZonesRepository     (zones.json)    │
                  │ • known_faces/<name>/*.jpg            │
                  └───────────────────────────────────────┘
```

## 5.2. Шари детально

### 5.2.1. UI Layer (`app/ui/`)

Основа: `MainWindow` з `QTabWidget`. Кожна вкладка — окремий `QWidget`-нащадок.
Вкладки не знають один про одного — комунікують через `Services` (DI).

| Файл | Призначення |
|------|-------------|
| `main_window.py` | Збирає вкладки, меню, обробка закриття |
| `tabs/live_tab.py` | Live-перегляд + керування детекторами |
| `tabs/persons_tab.py` | CRUD whitelist, статистика появ |
| `tabs/zones_tab.py` | Редактор полігональних зон |
| `tabs/events_tab.py` | Журнал подій з фільтрами + PDF-експорт |
| `tabs/statistics_tab.py` | Live-графіки агрегатів |
| `tabs/settings_tab.py` | Налаштування з поясненнями |
| `widgets/camera_view.py` | Віджет з QPixmap-display'ом кадру + alert flash |
| `widgets/clip_player.py` | QMediaPlayer для перегляду кліпів алертів |
| `widgets/zone_canvas.py` | QPainter-canvas для редагування полігонів |
| `icon.py` | Програмне створення іконки додатку |

### 5.2.2. Services (`app/services.py`)

Єдиний клас `Services`, що **компонує** усі залежності. Всі вкладки отримують
один і той самий інстанс через конструктор.

Властивості lazy-завантаження:
- `person_detector()` створюється при першому виклику (бо завантаження YOLO ~2 сек).
- `face_recognizer()` — аналогічно, бо YuNet + SFace — ~2 сек і 38+ MB пам'яті.
- `zones()` lazy — джерело істини в `zones.json`.

### 5.2.3. Core (`app/core/`)

Базові типи і логіка обробки потоку:

| Файл | Що містить |
|------|-----------|
| `frame.py` | `Frame(image: ndarray, timestamp, index)` — атомарний кадр |
| `types.py` | `Detection`, `ProcessingResult` — типи виводу детекторів |
| `pipeline.py` | `DetectionPipeline` — оркеструє детектори + трекер + зони + overlay |
| `zones.py` | `Zone(name, points)` — полігон з методом `contains()` |
| `video_source.py` | Абстракція над USB / RTSP / файлом (`OpenCVVideoSource`) |
| `video_worker.py` | `QThread`, що крутить read-loop і емітить `result_ready` |
| `settings.py` | `Settings` dataclass — всі налаштування |
| `sightings_tracker.py` | Дебаунс-трекер появ відомих персон |
| `alert_event.py` | `AlertEvent` — одна подія алерту |

### 5.2.4. Detectors (`app/detectors/`)

| Файл | Що містить |
|------|-----------|
| `person_detector.py` | YOLO11n + класи person |
| `face_recognizer.py` | YuNet + SFace + cosine-сматч з whitelist |
| `tracker.py` | Обгортка `supervision.ByteTrack` |
| `_yolo_utils.py` | Хелпер для шляху до ваг моделі |

Усі детектори імплементують протокол:
```python
class Detector(Protocol):
    def detect(self, frame: Frame) -> list[Detection]: ...
```

### 5.2.5. Alerts (`app/alerts/`)

| Файл | Що містить |
|------|-----------|
| `alert_manager.py` | `AlertManager`, всі правила (`UnknownFaceRule`, `ZoneIntrusionRule`, `LoiteringRule`), cooldown |
| `clip_manager.py` | Кільцевий буфер + запис відео-кліпів навколо моменту події |
| `sound.py` | `SoundPlayer` (beep) і `TTSPlayer` (pyttsx3) |

### 5.2.6. Storage (`app/storage/`)

| Файл | Призначення |
|------|-------------|
| `events_repo.py` | SQLite-репозиторій журналу подій + агрегації |
| `persons_repo.py` | SQLite-репозиторій лічильника появ персон |
| `settings_repo.py` | JSON-серіалізація `Settings` |
| `zones_repo.py` | JSON-серіалізація `list[Zone]` |

### 5.2.7. Reports (`app/reports/`)

`pdf_exporter.py` — формує HTML-звіт з даних `EventsRepository` і друкує його в
PDF через `QTextDocument` + `QPrinter`.

## 5.3. Потік даних в реальному часі

Найважливіший потік — обробка одного кадра. Послідовність:

```
┌────────────┐
│ Camera /   │
│ RTSP / file│
└─────┬──────┘
      │ 1. cv2.VideoCapture.read()
      ▼
┌────────────────────────────────────┐
│ OpenCVVideoSource (in QThread)     │
│   .read() ─► Frame(image, ts, idx) │
└─────────────┬──────────────────────┘
              │ 2. в циклі VideoWorker.run()
              ▼
┌────────────────────────────────────────────────┐
│ DetectionPipeline.process(frame):              │
│   ─ for detector in detectors:                 │
│        detections += detector.detect(frame)    │
│   ─ if tracker: tracker.update(detections, …)  │
│   ─ for det × zone: zone.contains(det.bot.cent)│
│   ─ image = draw_overlay(frame.image, …)       │
│   ─ return ProcessingResult                    │
└─────────────┬──────────────────────────────────┘
              │ 3. emit result_ready (Qt signal)
              ▼
┌────────────────────────────────────────────────┐
│ LiveTab._on_result(result):                    │
│   ─ camera_view.display_frame(result.image)    │
│   ─ counts label                               │
│   ─ services.alerts.on_frame(result)           │
│   ─ services.sightings.on_frame(result)        │
└─────────────┬──────────────────────────────────┘
              │ 4. для кожного правила алертів
              ▼
┌────────────────────────────────────────────────┐
│ AlertManager.on_frame(result):                 │
│   ─ clip_manager.push_frame(image, ts)         │
│   ─ for rule: rule.evaluate(result, ts)        │
│   ─ apply cooldown per-kind                    │
│   ─ for ev in fired:                           │
│        clip_manager.trigger(...)               │
│        sound/tts (опційно)                     │
│        events_repo.save(ev)                    │
│        emit alert_fired (Qt signal)            │
└─────────────┬──────────────────────────────────┘
              │ 5. emit alert_fired
              ▼
┌────────────────────────────────────────────────┐
│ LiveTab._on_alert(ev):                         │
│   ─ показати банер (5 сек)                     │
│   ─ camera_view.trigger_alert() (червона рамка)│
└────────────────────────────────────────────────┘
```

Важливо: пункти 1-2 виконуються в `VideoWorker` (QThread), а 3-5 — в UI-потоці.
Перехід між потоками — через Qt signals (`result_ready`, `alert_fired`).
Це гарантує thread-safety без явних м'ютексів.

## 5.4. Threading-модель

```
┌──────────────────┐               ┌──────────────────┐
│  GUI thread      │               │  VideoWorker     │
│  (Qt event loop) │               │  (QThread)       │
│                  │               │                  │
│  - QApplication  │               │  - while running:│
│  - Widgets       │   signals     │      read()      │
│  - Settings UI   │ ◄──────────── │      process()   │
│  - Banner        │               │      emit ready  │
│  - Statistics    │               │                  │
│  - alerts.signal │               │                  │
└──────────────────┘               └──────────────────┘
        │
        │  alert_fired signal
        │
        ▼
┌──────────────────┐
│ Audio threads    │ (simpleaudio внутрішньо)
└──────────────────┘
┌──────────────────┐
│ TTS thread       │ (pyttsx3 з власним потоком)
└──────────────────┘
```

GIL не є проблемою, бо:
- `cv2.VideoCapture.read()` звільняє GIL (C++ всередині).
- YOLO inference у `torch.cuda` — звільняє GIL.
- OpenCV operations — звільняють GIL.

Тому VideoWorker і UI-потік реально працюють паралельно.

## 5.5. Принципи, яких дотримується архітектура

### 5.5.1. Single Responsibility

Кожен клас вирішує одну задачу. Наприклад:
- `ClipManager` — лише запис відео.
- `AlertManager` — оркестрація правил і diффузія в sink'и.
- `EventsRepository` — лише робота з БД.

### 5.5.2. Dependency Injection через `Services`

UI-вкладки отримують `Services` через конструктор. Жоден widget не імпортує
конкретні детектори чи репозиторії:

```python
class LiveTab(QWidget):
    def __init__(self, services: Services) -> None:
        ...
```

Це дозволить у майбутньому замінити моделі (наприклад, YOLO11 → YOLO12) без
зміни UI.

### 5.5.3. Protocol-based contracts

`Detector`, `FrameProcessor`, `Tracker`, `AlertRule` — все це Python-протоколи.
Підставити свою імплементацію можна без наслідування — достатньо мати методи
з відповідною сигнатурою.

### 5.5.4. Lazy initialization для важких ресурсів

Моделі завантажуються тільки тоді, коли вони реально потрібні:
- Якщо користувач не вмикав чекбокс «Обличчя» в Live — SFace не завантажиться.
- Якщо користувач не відкривав вкладку «Персони» — face_recognizer не завантажиться.

Це робить запуск застосунку миттєвим (~ 0.5 сек до першого вікна).

### 5.5.5. Stateless rules where possible

Правила алертів не зберігають стан між викликами **там, де це не потрібно**:
- `ZoneIntrusionRule` — stateless.
- `UnknownFaceRule` — stateful (deque останніх кадрів для smoothing).
- `LoiteringRule` — stateful (треки у зонах).

Stateful-правила мають метод `reset()`, який викликається при відключенні
джерела (`AlertManager.reset()`).

## 5.6. Точки розширення

| Що додати | Де |
|-----------|-----|
| Новий тип детектора (наприклад, transport vehicle) | Реалізувати `Detector`-протокол у `app/detectors/` |
| Нове правило алерту | Реалізувати `AlertRule`-протокол у `app/alerts/alert_manager.py` |
| Інше джерело відео (RTMP, MJPEG-stream) | Спадкоємець `VideoSource` у `app/core/video_source.py` |
| Інший тип звіту | Окремий модуль у `app/reports/` |
| Інша БД для подій | Імплементація з тим самим інтерфейсом, що й `EventsRepository` |
| Нова вкладка | `QWidget`-нащадок з конструктором `(services: Services)` + реєстрація у `MainWindow` |
