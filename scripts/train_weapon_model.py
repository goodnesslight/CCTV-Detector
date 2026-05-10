"""
Дообучення YOLO11n під детекцію холодної зброї.

ЯК КОРИСТУВАТИСЯ:

  1. Знайди датасет на https://universe.roboflow.com (пошук 'knife detection',
     'weapon detection'). Критерії для дипломної роботи:
       - 5-20K розмічених зображень
       - реалістичні сцени (CCTV, ручні сценарії), а не лише студійні
       - є train / valid / test split

  2. На сторінці датасету "Show download code" — випиши workspace/project/version
     зі сніпета (або з URL: universe.roboflow.com/<workspace>/<project>).

  3. Встанови roboflow (один раз) і завантаж датасет helper-скриптом
     (він використовує API-ключ з .env):

         pip install roboflow
         python scripts/download_weapon_dataset.py <workspace> <project> <version>

     Наприкінці скрипт повідомить повний шлях до data.yaml.

  4. Запусти тренування:
         python scripts/train_weapon_model.py "<шлях до data.yaml>"

  5. Після завершення (~30 хв на RTX 3060) найкращі ваги автоматично
     скопіюються в data/models/weapons.pt — WeaponDetector підхопить
     їх при наступному запуску застосунку.

ВИХІДНІ АРТЕФАКТИ ДЛЯ ДИПЛОМА:
  - data/models/weapons.pt — фінальні ваги
  - runs/detect/<name>/results.png — графіки навчання (loss, mAP за епохами)
  - runs/detect/<name>/confusion_matrix.png — матриця помилок на val-сеті
  - У консоль друкуються фінальні precision / recall / mAP50 / mAP50-95

ПРАПОРЦІ:
  --epochs N      кількість епох (default 50; для швидкого тесту — 20)
  --imgsz N       розмір входу моделі (default 640)
  --batch N       batch size (default 16, влазить у 12 ГБ RTX 3060)
  --base PATH     базова модель (default yolo11n.pt; для кращої точності
                  використовуй yolo11s.pt — повільніше, але точніше)
  --name NAME     ім'я запуску всередині runs/detect/ (default weapons_run)
  --device DEV    GPU id або 'cpu' (default 0)
  --output FILE   ім'я файлу ваг у data/models/ (default weapons.pt)
"""
import argparse
import shutil
import sys
from pathlib import Path

# Гарантуємо корінь проекту в sys.path щоб `from app...` працювало як зі скрипта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ultralytics import YOLO  # noqa: E402

from app.config import MODELS_DIR  # noqa: E402
from app.detectors._yolo_utils import ensure_yolo_model  # noqa: E402


def _format_metric(metrics: dict, key: str) -> str:
    val = metrics.get(key)
    if isinstance(val, (int, float)):
        return f"{val:.4f}"
    return "N/A"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLO11n on a YOLO-format weapon dataset."
    )
    parser.add_argument("data_yaml", type=Path,
                        help="Шлях до data.yaml датасету (формат YOLO)")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--base", type=str, default="yolo11n.pt")
    parser.add_argument("--name", type=str, default="weapons_run")
    parser.add_argument("--device", type=str, default="0",
                        help="GPU id (наприклад '0') або 'cpu'")
    parser.add_argument("--output", type=str, default="weapons.pt",
                        help="Ім'я файлу ваг у data/models/ (default: weapons.pt).")
    args = parser.parse_args()

    if not args.data_yaml.exists():
        print(f"ERROR: data.yaml не знайдено: {args.data_yaml}")
        return 1

    base_path = ensure_yolo_model(args.base)

    print("=" * 64)
    print(f"  Базова модель: {base_path}")
    print(f"  Датасет:       {args.data_yaml}")
    print(f"  Епох:          {args.epochs}")
    print(f"  Розмір входу:  {args.imgsz}")
    print(f"  Batch size:    {args.batch}")
    print(f"  Пристрій:      {args.device}")
    print("=" * 64)
    print()

    model = YOLO(str(base_path))
    results = model.train(
        data=str(args.data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
        verbose=True,
        plots=True,
    )

    save_dir = Path(results.save_dir) if hasattr(results, "save_dir") else None
    if save_dir is None or not save_dir.exists():
        print("ERROR: не вдалося визначити save_dir тренування")
        return 1

    best_weights = save_dir / "weights" / "best.pt"
    if not best_weights.exists():
        print(f"ERROR: best.pt не знайдено в {save_dir / 'weights'}")
        return 1

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / args.output
    shutil.copy2(best_weights, target)

    print()
    print("=" * 64)
    print(f"  Ваги збережено: {target}")
    print(f"  Артефакти:      {save_dir}")
    print("=" * 64)

    print()
    print("Фінальна валідація на val-сеті:")
    val_results = model.val(data=str(args.data_yaml))
    metrics = getattr(val_results, "results_dict", {}) or {}

    print()
    print("=" * 64)
    print("  МЕТРИКИ (для розділу 'Експерименти' у дипломі)")
    print("=" * 64)
    print(f"  Precision  : {_format_metric(metrics, 'metrics/precision(B)')}")
    print(f"  Recall     : {_format_metric(metrics, 'metrics/recall(B)')}")
    print(f"  mAP@0.5    : {_format_metric(metrics, 'metrics/mAP50(B)')}")
    print(f"  mAP@0.5:.95: {_format_metric(metrics, 'metrics/mAP50-95(B)')}")
    print("=" * 64)
    print()
    print(f"  Графіки навчання:    {save_dir / 'results.png'}")
    print(f"  Confusion matrix:    {save_dir / 'confusion_matrix.png'}")
    print(f"  Приклади передбачень: {save_dir / 'val_batch0_pred.jpg'}")
    print()
    print("Перезапусти застосунок — WeaponDetector автоматично завантажить")
    print(f"{target.name} замість COCO-fallback.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
