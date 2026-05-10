# Система безпеки приміщення на базі відеоспостереження та штучного інтелекту

Дипломний проект. Десктоп-застосунок (Windows / Linux) для інтелектуального відеоспостереження
у приміщенні з опрацюванням потоку в реальному часі засобами комп'ютерного зору.

> Автор: **Майборода Євгеній Олександрович**, гр. ІК-22
> Версія: 1.0.0 · Платформа: Windows 11 (тестовано на RTX 3060)

---

## Що вміє система

- **Детекція людей** у кадрі (YOLO11n) із візуалізацією bbox і лічильником.
- **Розпізнавання облич** з whitelist (YuNet + SFace) — поділ на «знайомий» / «незнайомий».
- **Зони уваги** — довільні полігони, з фіксацією входження детекцій.
- **Loitering** — тривале перебування у зоні (трекінг ByteTrack + правило часу).
- **Алерти** — банер у вікні, beep, опційно TTS, відеокліп навколо моменту події.
- **Журнал подій** з фільтрами + експорт у **PDF**.
- **Статистика** — графіки активності, агрегація за типом / зоною.
- **Облік появ персон** — лічильник + час останньої появи кожної відомої особи.
- **Збереження стану** між запусками: налаштування, зони, whitelist, історія подій.

## Швидкий старт

```bash
python -m venv .venv
.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python main.py
```

Деталі див. у [docs/09-installation.md](docs/09-installation.md).

## Документація

Документація розбита на 10 тематичних розділів у директорії [`docs/`](docs):

| № | Файл | Про що |
|---|------|--------|
| 01 | [problem-and-relevance.md](docs/01-problem-and-relevance.md) | Проблема, цільова аудиторія, актуальність |
| 02 | [competitors.md](docs/02-competitors.md) | Огляд існуючих рішень, відмінності |
| 03 | [tech-stack.md](docs/03-tech-stack.md) | Стек технологій, обґрунтування вибору Python |
| 04 | [ai-models.md](docs/04-ai-models.md) | Моделі ШІ: YOLO11, YuNet, SFace, ByteTrack |
| 05 | [architecture.md](docs/05-architecture.md) | Архітектура застосунку, шари, діаграми |
| 06 | [algorithms.md](docs/06-algorithms.md) | Алгоритми (pipeline, smoothing, loitering) |
| 07 | [features.md](docs/07-features.md) | Опис вкладок та функцій |
| 08 | [data-storage.md](docs/08-data-storage.md) | Структура даних, БД, файли |
| 09 | [installation.md](docs/09-installation.md) | Встановлення, запуск, перший запуск |
| 10 | [implementation-notes.md](docs/10-implementation-notes.md) | Технічні нюанси реалізації |

## Структура репозиторію

```
OPERATION_ARGUS/
├── main.py                # Точка входу
├── requirements.txt       # Залежності
├── app/
│   ├── core/              # Базові типи, pipeline, налаштування, трекінг
│   ├── detectors/         # YOLO, FaceRecognizer (YuNet+SFace), ByteTrack
│   ├── alerts/            # AlertManager, ClipManager, sound, TTS
│   ├── storage/           # SQLite repositories, JSON-конфіги
│   ├── reports/           # Експорт PDF
│   ├── ui/                # PySide6 GUI: вкладки, віджети, MainWindow
│   ├── services.py        # Композиція компонентів
│   └── config.py          # Шляхи, константи додатку
├── data/                  # Runtime (gitignored): моделі, кліпи, БД, конфіги
├── assets/                # Іконки, звуки
└── docs/                  # Документація проекту
```

## Ліцензії моделей

- **YOLO11**: Ultralytics, AGPL-3.0 (для дипломної некомерційної роботи прийнятно).
- **YuNet, SFace**: OpenCV Zoo, Apache 2.0.
- **ByteTrack** (через `supervision`): MIT.
