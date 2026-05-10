# 08. Структура даних та зберігання

Усі persistent-дані живуть у директорії `data/` у корені проекту. Структура:

```
data/
├── models/              # ваги моделей (auto-download при першому запуску)
│   ├── yolo11n.pt                              ← YOLO11 nano
│   ├── face_detection_yunet_2023mar.onnx       ← YuNet
│   └── face_recognition_sface_2021dec.onnx     ← SFace
├── known_faces/         # whitelist з фото відомих осіб
│   ├── Іван/
│   │   ├── photo1.jpg
│   │   └── photo2.jpg
│   └── Олена/
│       └── work.png
├── unknown_faces/       # знімки облич з unknown_face алертів
│   ├── 20260510-142345_a8f31bc2.jpg
│   └── 20260510-141812_e9c1a4d8.jpg
├── clips/               # відео-кліпи навколо алертів
│   ├── 20260510-142345_unknown_face_a8f3.mp4
│   └── 20260510-141812_zone_Касса_e9c1.mp4
├── events.db            # SQLite БД журналу подій + лічильника появ
├── activity_heatmap.npy # накопичена теплова карта руху людей
├── settings.json        # зберігання Settings
└── zones.json           # зберігання list[Zone]
```

Усі ці файли в `.gitignore` — це **runtime-стан**, не код.

## 8.1. SQLite (events.db)

Одна БД з двома таблицями. Шлях — `app.config.DB_PATH = data/events.db`.

### 8.1.1. Таблиця `events`

```sql
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    timestamp       REAL    NOT NULL,
    kind            TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    detail          TEXT,
    zone_name       TEXT,
    bbox_x1         INTEGER,
    bbox_y1         INTEGER,
    bbox_x2         INTEGER,
    bbox_y2         INTEGER,
    clip_path       TEXT,
    snapshot_path   TEXT,
    face_embedding  BLOB
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
```

| Колонка | Опис |
|---------|------|
| `id` | UUID-prefix (12 hex chars), генерується при створенні AlertEvent |
| `timestamp` | Unix-time у секундах (float) |
| `kind` | Машинне ім'я типу (`unknown_face`, `zone:Каса`, `loitering:Каса`) |
| `title` | UI-друк («Незнайоме обличчя», «Вторгнення в зону», ...) |
| `detail` | Деталь («в кадрі: 2», «5.3с, трек #7», ...) |
| `zone_name` | Назва зони, якщо релевантно |
| `bbox_*` | Координати bbox первинної детекції |
| `clip_path` | Абсолютний шлях до MP4-кліпу або NULL |
| `snapshot_path` | Абсолютний шлях до JPG зі знімком обличчя (тільки для `unknown_face`) або NULL |
| `face_embedding` | 128 × float32 = 512 байт SFace-вектора (тільки для `unknown_face`) або NULL |

### Migration для існуючих БД

`_init_schema()` після `CREATE TABLE` перевіряє через `PRAGMA table_info`,
чи є колонки `face_embedding` і `snapshot_path`. Якщо ні — виконує
`ALTER TABLE events ADD COLUMN ...`. Старі БД (без цих колонок) підхопляться
без втрат, нові події заповнять колонки.

### 8.1.2. Таблиця `person_sightings`

```sql
CREATE TABLE IF NOT EXISTS person_sightings (
    name        TEXT PRIMARY KEY,
    total       INTEGER NOT NULL DEFAULT 0,
    last_seen   REAL
);
```

| Колонка | Опис |
|---------|------|
| `name` | Унікальне ім'я персони (як у whitelist) |
| `total` | Кількість окремих появ (з 30-сек дебаунсом) |
| `last_seen` | Unix-time останньої появи |

UPSERT через `INSERT … ON CONFLICT DO UPDATE`:

```sql
INSERT INTO person_sightings (name, total, last_seen)
VALUES (?, 1, ?)
ON CONFLICT(name) DO UPDATE SET
    total = total + 1,
    last_seen = excluded.last_seen
```

### 8.1.3. Чому SQLite

- Single-writer (UI-потік) — немає concurrent issues.
- Embed — нема серверу, нема порту, нема окремого процесу.
- Schema-flexible — для дипломної версії ALTER не потрібен.
- Швидкість — 5000+ insert/sec, що більше за частоту алертів на порядки.

## 8.2. JSON-файли

### 8.2.1. `data/settings.json`

Серіалізований `Settings` dataclass:

```json
{
  "yolo_conf_threshold": 0.4,
  "face_match_threshold": 0.4,
  "face_det_threshold": 0.7,
  "live_person_enabled": true,
  "live_face_enabled": true,
  "live_tracking_enabled": false,
  "alert_cooldown_seconds": 10.0,
  "loitering_threshold_seconds": 5.0,
  "sighting_cooldown_seconds": 30.0,
  "beep_enabled": true,
  "tts_enabled": false,
  "tts_language": "uk",
  "clip_pre_seconds": 2.0,
  "clip_post_seconds": 5.0,
  "privacy_blur_unknown": false,
  "activity_heatmap_enabled": false
}
```

#### Migration safety

`SettingsRepository.load()` фільтрує невідомі ключі:

```python
valid_keys = {f.name for f in fields(Settings)}
kwargs = {k: v for k, v in raw.items() if k in valid_keys}
return Settings(**kwargs)
```

Тому видалення поля з dataclass не зламає завантаження старого `settings.json`.
Невідоме поле просто ігнорується, а наступний save його витре.

### 8.2.2. `data/zones.json`

Серіалізований `list[Zone]`:

```json
[
  {
    "name": "Каса",
    "points": [[120, 200], [340, 200], [340, 400], [120, 400]]
  },
  {
    "name": "Серверна",
    "points": [[450, 100], [600, 100], [600, 250], [450, 250]]
  }
]
```

Поінти зберігаються в координатах кадру з якого зробили snapshot. Якщо
розрізнення камери змінилось — зони доведеться передзняти.

## 8.3. Файлова структура — детальніше

### 8.3.1. `data/models/`

Auto-download при першому запуску:
- `yolo11n.pt` — Ultralytics завантажує самотужки при першому використанні YOLO.
- YuNet/SFace — `_ensure_model()` у `face_recognizer.py` тягне з GitHub raw,
  якщо файлу немає.

Розмір:
- `yolo11n.pt` — ~5 MB
- `yunet` — ~232 KB
- `sface` — ~38 MB

Загалом ~45 MB при першому запуску.

### 8.3.2. `data/known_faces/<name>/<photo>.jpg`

Структура: одна папка на персону, ім'я папки = ім'я персони. Будь-які
підтримувані формати (`.jpg, .jpeg, .png, .bmp, .webp`).

При додаванні фото через UI — copy у відповідну папку (з суфіксом `_1`, `_2`
у разі колізії імен).

### 8.3.3. `data/clips/`

MP4-кліпи (codec mp4v, 25 fps). Ім'я: `<YYYYMMDD-HHMMSS>_<safe_kind>_<id>.mp4`.

При потребі звільнити місце — можна безпечно видаляти файли. Записи в БД
залишаться, але `clip_path` стане «orphan» — UI просто не покаже плеєр.

### 8.3.4. `data/unknown_faces/`

JPG-знімки обличчя для `unknown_face`-алертів. Кропаються з оригінального
кадру (без overlay) з 20% padding для контексту.

Ім'я: `<YYYYMMDD-HHMMSS>_<id8>.jpg`.

Шлях зберігається в `events.snapshot_path`; видалення JPG залишає колонку
у БД (orphan), UI у такому разі покаже placeholder.

### 8.3.5. `data/activity_heatmap.npy`

NumPy-масив `float32` зі сіткою накопиченої активності. Розмір залежить
від першого кадру (W/4 × H/4). Зберігається кожні 300 кадрів та при
shutdown через `np.save()`. При завантаженні застосунку — `np.load()`.

Якщо файл відсутній — стартуємо з порожньої сітки. Якщо розмір кадру змінився
між сесіями — сітка автоматично перебудовується (старі дані відкидаються).

## 8.4. Життєвий цикл даних

```
┌──────────────────────────────────────────────────────────────┐
│            Початковий стан (свіжа інсталяція)                │
└──────────────────────────────────────────────────────────────┘
   data/ ─ порожня

   ↓  python main.py

   data/models/  → завантажуються моделі при першому use
   data/settings.json → створиться при першому save
   data/zones.json → створиться при першому save
   data/events.db → створиться при першому AlertManager.__init__

┌──────────────────────────────────────────────────────────────┐
│            Робочий стан (після N сесій)                      │
└──────────────────────────────────────────────────────────────┘
   data/known_faces/ ─ whitelist
   data/clips/ ─ кліпи алертів (можна почистити вручну)
   data/events.db ─ event log (можна очистити з UI: Settings → Скинути журнал)
```

## 8.5. Резервне копіювання

Для повного бекапу достатньо скопіювати `data/`:
- `events.db` — журнал.
- `settings.json` + `zones.json` — конфіги.
- `known_faces/` — whitelist.
- `clips/` — кліпи (опційно, якщо мало місця).

`models/` — можна не бекапити, бо завантажиться знову.

## 8.6. Захист персональних даних

Усе залишається **локально**. Жодного мережевого запиту після завантаження
моделей при першому запуску.

`.gitignore` блокує комміт:

```gitignore
data/models/
data/clips/
data/known_faces/
data/unknown_faces/
data/activity_heatmap.npy
data/events.db
data/events.db-journal
data/events.db-shm
data/events.db-wal
data/settings.json
data/zones.json
.env
```

Видалення персони → `shutil.rmtree(data/known_faces/<name>)` + `DELETE FROM
person_sightings WHERE name = ?`. Embeddings у пам'яті теж очищуються
(`self._whitelist.pop(name)`).

Для GDPR-сумісного режиму у Settings → ☑ «Розмивати незнайомі обличчя» —
тоді у Live й кліпах обличчя сторонніх pixelate-розмиваються.

## 8.7. Сценарій передачі іншому користувачу

1. Скопіювати папку проекту разом з `data/` — отримує точно такий самий стан.
2. Або: тільки код + `requirements.txt` — отримає чистий екземпляр, де
   моделі завантажаться при першому запуску, а `known_faces`, `events.db`,
   `clips/` — порожні.
