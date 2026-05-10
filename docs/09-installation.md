# 09. Встановлення та запуск

## 9.1. Системні вимоги

| Параметр | Мінімум | Рекомендовано |
|----------|---------|---------------|
| ОС | Windows 10 / Ubuntu 22.04+ | Windows 11 |
| Python | 3.10 | 3.12 |
| RAM | 8 ГБ | 16+ ГБ |
| GPU | Інтегрована (CPU mode) | NVIDIA RTX 3050+ з ≥ 6 ГБ VRAM |
| Диск | 5 ГБ | 50+ ГБ для тривалих архівів кліпів |
| Камера | USB UVC або RTSP | 1080p IP-камера |

> Тестовано на: Windows 11, Python 3.12, RTX 3060, 32 ГБ RAM.

## 9.2. Покрокова установка (Windows)

### 9.2.1. Python та венв

```powershell
# Перевірити версію
python --version            # повинно бути 3.10+

# Створити venv у корені проекту
python -m venv .venv

# Активувати
.venv\Scripts\activate
```

### 9.2.2. PyTorch з CUDA

PyTorch має власний індекс пакетів — встановлюємо ОКРЕМО:

```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> Без CUDA-варіанту все одно працюватиме, але YOLO буде на CPU
> (~5-8 FPS замість 30-60). Для дипломної демо рекомендується CUDA.

### 9.2.3. Решта залежностей

```powershell
pip install -r requirements.txt
```

Це підтягне:
- PySide6 (Qt 6 GUI),
- opencv-python (CV + YuNet/SFace),
- ultralytics (YOLO),
- supervision (ByteTrack),
- pyttsx3 (TTS),
- simpleaudio (звуки),
- pyqtgraph (графіки),
- Pillow, NumPy.

Загальний розмір залежностей після встановлення: ~3 ГБ (через PyTorch + CUDA).

### 9.2.4. Перший запуск

```powershell
python main.py
```

При першому запуску:
1. Завантажиться `yolo11n.pt` (~5 MB) у `data/models/` — займає 1-3 сек.
2. При першому використанні вкладки «Персони» завантажаться YuNet+SFace
   (~38 MB) — займає ~3 сек.

Жодних додаткових скриптів запускати не треба — БД, конфіги, директорії
створяться автоматично.

## 9.3. Встановлення (Linux)

### 9.3.1. Системні пакети (Ubuntu 22.04+)

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
sudo apt install libxcb-cursor0           # для PySide6
sudo apt install espeak                   # для pyttsx3
```

### 9.3.2. Python-залежності

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

### 9.3.3. Запуск

```bash
python main.py
```

Камера `/dev/video0` використовується як index 0 в `cv2.VideoCapture`.

## 9.4. Що робити при першому запуску

### 9.4.1. Live-тест

1. Вкладка **«Пряма трансляція»**.
2. Джерело: `USB-камера`, спец = `0` (типово для першої камери).
3. Чекбокс **«Люди (YOLO)»** залишити увімкненим.
4. Натиснути **«Підключитися»**.
5. Перевірити, що bounding box з'являється навколо людей.

### 9.4.2. Whitelist облич

1. Вкладка **«Персони»** → **«Завантажити базу облич»** (перший раз — підкачка моделей).
2. **«Додати персону...»** → ввести ім'я → обрати фото з обличчям.
3. Повернутись на **«Пряма трансляція»**, увімкнути **«Обличчя (YuNet+SFace)»**.
4. Стати перед камерою — повинен з'явитись підпис з вашим ім'ям.

### 9.4.3. Зони

1. Вкладка **«Зони»** → **«Зробити знімок з камери»** (потрібно щоб Live була підключена).
2. **«Нова зона...»** → ім'я.
3. Кликати на канві ЛКМ для точок, ПКМ — закрити полігон.
4. Повернутись на Live → у momenта входження детекції в зону → bbox стане червоним.

### 9.4.4. Алерти

При появі будь-якої події (людина в зоні, незнайоме обличчя, loitering):
- Червоний banner вгорі.
- Beep (якщо увімкнено в Settings).
- TTS-оголошення (якщо увімкнено).
- Кліп зберігається в `data/clips/`.

Передивитися можна на вкладці **«Події»**.

## 9.5. Можливі проблеми

### 9.5.1. `ImportError: DLL load failed` (Windows)

Зазвичай — Visual C++ Redistributable. Завантажте з
`https://aka.ms/vs/17/release/vc_redist.x64.exe`.

### 9.5.2. `cv2.VideoCapture` не відкриває камеру

- На Windows: перевірити дозвіл на доступ до камери (Параметри → Конфіденційність → Камера).
- USB-камеру вже може використовувати інший застосунок (Skype, Teams) — закрити.
- Спробувати інший index: `1` замість `0`.

### 9.5.3. RTSP не відкривається

Формат URL: `rtsp://user:pass@ip:port/path`. На Hikvision/Dahua типово
`rtsp://admin:password@192.168.1.108:554/Streaming/Channels/101`.

При проблемах: спочатку перевірити в VLC — якщо там не працює, проблема не
в нашому застосунку.

### 9.5.4. YOLO не використовує GPU

Перевірити в Python REPL:

```python
import torch
print(torch.cuda.is_available())  # повинно бути True
```

Якщо False — CUDA не встановлена або не та версія. Перевстановити torch
з правильним індексом.

### 9.5.5. Кадр не показується, лише статус «Підключено»

Можливо проблема з кодеком потоку. Спробувати `--verbose` режим в OpenCV
(встановити `OPENCV_LOG_LEVEL=DEBUG` змінну середовища) і подивитись логи.

### 9.5.6. PySide6 + supervision дає AttributeError при імпорті

Це відома проблема ланцюжка `supervision → matplotlib → dateutil → six.moves`.
У `main.py` робиться pre-import `supervision` ПЕРЕД PySide6, що вирішує
проблему. Якщо ви правите `main.py` — не міняйте порядок імпортів.

## 9.6. Структура запуску

```
python main.py
   │
   ├─ pre-import supervision (фікс для PySide6+torch)
   │
   ├─ QApplication(sys.argv)
   ├─ ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(...)  # Windows
   │
   ├─ MainWindow()
   │   ├─ Services()  ← створює AlertManager, репозиторії, Settings
   │   ├─ QTabWidget з 6 вкладок
   │   └─ menubar
   │
   └─ app.exec()  ← Qt main loop
```

## 9.7. Розгортання (для майбутнього)

Поза дипломним scope, але можливе:

### PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --windowed \
    --add-data "assets;assets" \
    --hidden-import "ultralytics" \
    --hidden-import "supervision" \
    main.py
```

Отримаєте exe-файл в `dist/`. Розмір: ~500 MB (PyTorch + CUDA — великі).

### Без CUDA (slim build)

Замість `torch+cu121` встановити CPU-only:

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

Розмір зменшиться до ~150 MB, але YOLO буде на CPU.

## 9.8. Видалення

```bash
# Видалити виртуальне середовище
rm -rf .venv      # Linux
rd /s /q .venv    # Windows

# Видалити runtime-дані
rm -rf data/

# Видалити проект
rm -rf OPERATION_ARGUS/
```

Жодних реєстрових ключів, системних служб або installer-ів. Чисте видалення.
