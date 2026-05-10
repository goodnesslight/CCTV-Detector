# 03. Технологічний стек

## 3.1. Зведена таблиця

| Шар | Технологія | Версія | Призначення |
|-----|-----------|--------|-------------|
| Мова | Python | 3.12 | Загальне програмування |
| GUI | PySide6 (Qt 6) | ≥ 6.6 | Десктопний інтерфейс |
| CV-low-level | OpenCV (`opencv-python`) | ≥ 4.9 | Зчитування відео, операції з кадрами, face-detection/recognition (YuNet/SFace) |
| Чисельні обчислення | NumPy | < 2.0 | Робота з кадрами як з масивами |
| Текст з кирилицею | Pillow (PIL) | ≥ 10.0 | Render Cyrillic-підписів на кадрах |
| Object detection | Ultralytics YOLO | ≥ 8.2 | YOLO11n для людей |
| GPU-фреймворк | PyTorch + CUDA 12.1 | torch ≥ 2.0 | Бекенд для YOLO |
| Tracking | supervision | ≥ 0.21 | ByteTrack-обгортка |
| TTS | pyttsx3 | ≥ 2.90 | Голосові оголошення |
| Beep | simpleaudio | ≥ 1.0 | Аварійні звуки (безпечніше за winsound) |
| Графіки | pyqtgraph | ≥ 0.13 | Live-графіки на вкладці «Статистика» |
| БД | SQLite (stdlib `sqlite3`) | вбудовано | Журнал подій + статистика появ |
| Звіти | Qt Print Support | у складі PySide6 | Експорт PDF (HTML → QTextDocument → QPrinter) |

## 3.2. Чому саме Python

Це найважливіше технічне рішення проекту, тому розглянуто детально.

### 3.2.1. Альтернативи, які розглядалися

| Мова / стек | За | Проти | Підсумок |
|-------------|-----|-------|----------|
| **C++** + Qt + OpenCV | Найкраща продуктивність, native FPS | Вища складність розробки; ML-екосистема (PyTorch, Ultralytics) має first-class API саме на Python; для дипломної реалізації витрати часу зростуть у 3–5 разів | Відхилено |
| **C#** + WPF + ML.NET / OpenCvSharp | Кращий Windows-UX, гарний UI-toolkit | ML.NET сильно відстає від PyTorch; YOLO/обличчя інтегруються через ONNX і втрачають частину функцій; немає прямого port'у `ultralytics` | Відхилено |
| **JavaScript / Electron** + TF.js | Кросплатформа, web-UI безкоштовно | TF.js на порядки повільніший за PyTorch+CUDA; нема нормального доступу до камер на десктопі; пам'ять Electron — окрема проблема | Відхилено |
| **Java / Kotlin** + JavaCV | Стабільний JVM, гарні GUI-toolkit'и | DL-екосистема (DJL) обмежена; нема `ultralytics`; нативна камера через JavaCV — менш стабільна | Відхилено |
| **Rust** + egui + tch-rs | Безпека, швидкість | Дуже мала ML-екосистема, відсутні готові face-моделі; криза часу на розробку | Відхилено |
| **Python** + PySide6 + Ultralytics + OpenCV | Усе вище — у вигляді мінусів С++ — обертається плюсами Python | Швидкість інференсу залежить від C++/CUDA-бекендів — отже немає реального overhead | **Обрано** |

### 3.2.2. Конкретні аргументи на користь Python

**1. ML-екосистема — first-class.**
- `pip install ultralytics` — і YOLO11 готовий до використання.
- `pip install opencv-python` — і YuNet+SFace доступні з коробки.
- `pip install supervision` — і ByteTrack працює.
- Аналогічна функціональність на C++/Java/Rust потребувала би тижнів інтеграції.

**2. Real-time продуктивність — не питання.**
Python — це фронт-енд для C++/CUDA-обчислень. Ось де реально витрачається час
на обробку одного кадру (1080p, RTX 3060):

```
┌──────────────────────────────┬───────┐
│ YOLO inference (CUDA)        │ 12 мс │  ← C++ + CUDA
│ FaceDetectorYN (CPU/CUDA)    │ 8 мс  │  ← C++
│ FaceRecognizerSF (CPU/CUDA)  │ 3 мс  │  ← C++
│ Pillow/cv2 overlay           │ 4 мс  │  ← C++
│ Qt signals + display         │ 1 мс  │  ← C++
│ Python glue code             │ <1 мс │  ← Python
├──────────────────────────────┼───────┤
│ Разом                        │ ~28 мс│  → 35 FPS
└──────────────────────────────┴───────┘
```

Отже Python-частина — менше 5% часу. Перехід на C++ дасть 0–2% приросту, втративши
60–70% швидкості розробки.

**3. PySide6 (Qt) — найзріліший крос-платформний UI на Python.**
- Native widgets під Windows (QListWidget, QTabWidget — виглядають як рідні).
- QThread для роботи у фоні без блокування UI.
- QPainter / QPixmap для відображення кадрів.
- QPrinter + QTextDocument — готовий PDF-експорт без зовнішніх бібліотек.
- Сигнали-слоти забезпечують thread-safety між робочим потоком (`VideoWorker`) і UI.

Альтернативи: Tkinter (потужність на нулі), Kivy (мобільний фокус), wxPython (менш активний), CustomTkinter (примітивний). PySide6 — єдиний серйозний десктоп-варіант.

**4. Розробка та діагностика — швидко.**
- REPL для експериментів з кадрами / моделями.
- `print(detections)` → миттєвий результат, без перекомпіляції.
- Hot-iteration циклу: змінив код → запустив → побачив. Цикл < 5 секунд.

**5. Знайомство користувача (студента) з мовою.**
Дипломна робота має бути **зрозумілою автору в кожній лінії**. Python — мова, з
якою студент знайомий найкраще, що дає змогу глибше зосередитися на алгоритмах
КЗ, ніж на синтаксисі.

### 3.2.3. Які мінуси Python приймаємо

- **GIL.** Один потік Python виконує байткод за раз. Обходимо тим, що тяжкі операції
  (YOLO inference, OpenCV decoding) звільняють GIL, бо виконуються у С/С++.
  Наш `VideoWorker` — `QThread`, що працює паралельно з UI; всередині нього
  — Python-код, що дзвонить native-бібліотеки.
- **Розповсюдження.** Розповсюдити Python-застосунок складніше, ніж .exe.
  Розв'язується PyInstaller'ом (передбачено для подальших ітерацій).
- **Залежності тяжкі.** PyTorch + CUDA — кілька гігабайт. Це data-science реальність.

## 3.3. Бібліотеки — детальніше

### 3.3.1. PySide6 (Qt 6)

- **Чому не PyQt5/6?** PySide6 — офіційні bindings від The Qt Company, ліцензія LGPL,
  дозволяє комерційне використання без проблем. PyQt — від Riverbank (GPL/комерц.).
  Для open-source проекту обидві ОК, але PySide6 — на майбутнє безпечніше.
- **Що використано:**
  - `QApplication`, `QMainWindow`, `QTabWidget`
  - `QThread` + сигнали для асинхронної обробки відео
  - `QPainter` + `QPixmap` для відмалювання кадрів (`CameraView`)
  - `QPolygon` для зон на canvas-віджеті
  - `QPrinter` + `QTextDocument` для PDF-експорту
  - `QMediaPlayer` для перегляду кліпів алертів

### 3.3.2. OpenCV (opencv-python)

- **Версія:** 4.9+ (через `pip`, prebuilt бінарники, без потреби збирати).
- **Що використано:**
  - `cv2.VideoCapture` — захоплення USB / RTSP / file.
  - `cv2.FaceDetectorYN` (YuNet) — детекція облич.
  - `cv2.FaceRecognizerSF` (SFace) — embedding-метрика для облич.
  - `cv2.pointPolygonTest` — тест точки в полігоні зони (без `shapely`).
  - `cv2.fillPoly`, `cv2.polylines` — малювання зон.
  - `cv2.VideoWriter` (mp4v) — запис кліпів алертів.
  - `cv2.cvtColor` — RGB ↔ BGR конверсії.

### 3.3.3. Ultralytics

- **Чому Ultralytics, а не stand-alone YOLO?** Він обгортає `torch`, дає простий
  API `.predict()`, керує завантаженням моделей, скриптами тренування — це
  економить тижні інтеграції.
- **Версія моделі:** YOLO11n — найновіша на момент розробки (2025), n = nano,
  ~3 MB параметрів, 5 MB файл, ~40 mAP@COCO.

### 3.3.4. supervision (Roboflow)

- Тонка обгортка над різними MOT-трекерами; нам потрібен лише ByteTrack.
- Альтернатива — interface `boxmot`, але `supervision` краще документований і
  має активну спільноту.

### 3.3.5. Pillow (PIL)

Використовується тільки для рендеру тексту з кирилицею: `cv2.putText` не
підтримує Unicode понад ASCII (рендерить "?????" замість українських літер).
Інших функцій PIL не використовуємо.

### 3.3.6. pyttsx3 + simpleaudio

- `pyttsx3` — offline TTS (SAPI5 на Windows, espeak на Linux). Працює без інтернету.
- `simpleaudio` — playback `.wav`-файлів без блокування. Замінив `winsound` з
  stdlib, бо він синхронний і блокує потік.

### 3.3.7. SQLite

- Stdlib (`sqlite3` модуль).
- Зберігає `events` (журнал алертів) і `person_sightings` (лічильник появ).
- **Чому не PostgreSQL/MongoDB?** Single-user desktop app, файлова БД ідеальна:
  немає окремого сервера, нема порту, нема reservation.

### 3.3.8. pyqtgraph

- Швидкий live-plot бекенд на Qt (на відміну від matplotlib, який використовує
  свій render).
- Використовується для графіків активності у вкладці «Статистика» (events-over-time,
  events-by-zone тощо).

## 3.4. Навіщо CUDA / GPU

YOLO11n на CPU дає ~5–8 FPS на 1080p. На RTX 3060 — 60+ FPS. Для real-time
відеоспостереження CPU-only недостатньо.

Stack: PyTorch ≥ 2.0 з CUDA 12.1 → `torch.cuda.is_available()` → `model.to('cuda')`.
Якщо GPU немає — fallback на CPU, з повідомленням у статус-рядок.

## 3.5. Системні вимоги

| Параметр | Мінімум | Рекомендовано |
|----------|---------|---------------|
| OS | Windows 10 / Ubuntu 22.04 | Windows 11 |
| Python | 3.10 | 3.12 |
| RAM | 8 ГБ | 16+ ГБ |
| GPU | Інтегрована (CPU mode) | NVIDIA RTX 3050+ з ≥ 6 ГБ VRAM |
| Диск | 5 ГБ (моделі + кліпи) | 50+ ГБ для тривалих записів |
| Камера | USB UVC або RTSP | 1080p IP-камера |
