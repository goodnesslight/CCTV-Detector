"""
Завантажує датасет з Roboflow Universe у datasets/ для подальшого
дообучення через scripts/train_weapon_model.py.

API-ключ береться з .env (змінна ROBOFLOW_API_KEY).

ЯК КОРИСТУВАТИСЯ:

  1. Знайди датасет на https://universe.roboflow.com (пошук 'knife detection',
     'weapon detection', 'cold weapon')

  2. На сторінці датасету відкрий блок "Show download code". У Python-сніпеті
     знайди три значення:

         rf.workspace("WORKSPACE_ID").project("PROJECT_ID").version(N)
                     ^^^^^^^^^^^^                ^^^^^^^^^         ^

     Вони ж містяться в URL: https://universe.roboflow.com/<WORKSPACE>/<PROJECT>/...

  3. Встанови roboflow (один раз):
         pip install roboflow

  4. Запусти цей скрипт:
         python scripts/download_weapon_dataset.py <WORKSPACE_ID> <PROJECT_ID> <VERSION>

     Приклад:
         python scripts/download_weapon_dataset.py knife-yzefb knife-detection-bohpw 3

  5. Після завантаження тобі скажуть точний шлях до data.yaml — копіюй його
     в команду тренування.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a Roboflow Universe dataset using API key from .env",
    )
    parser.add_argument("workspace", help="Workspace ID (з URL або snippet'а)")
    parser.add_argument("project", help="Project ID (з URL або snippet'а)")
    parser.add_argument("version", type=int, help="Номер версії датасету")
    parser.add_argument("--format", default="yolov8",
                        help="Формат вивантаження (default: yolov8)")
    parser.add_argument("--out", default="datasets",
                        help="Куди завантажувати (default: datasets/)")
    args = parser.parse_args()

    _load_env()
    api_key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ROBOFLOW_API_KEY не знайдено в .env")
        print("       Створи .env у корені проекту з рядком:")
        print("       ROBOFLOW_API_KEY=твій_ключ")
        return 1

    try:
        from roboflow import Roboflow
    except ImportError:
        print("ERROR: пакет 'roboflow' не встановлено. Запусти:")
        print("       pip install roboflow")
        return 1

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Workspace: {args.workspace}")
    print(f"  Project:   {args.project}")
    print(f"  Version:   {args.version}")
    print(f"  Format:    {args.format}")
    print(f"  Out:       {out_dir}")
    print()

    cwd = Path.cwd()
    os.chdir(out_dir)
    try:
        rf = Roboflow(api_key=api_key)
        project = rf.workspace(args.workspace).project(args.project)
        dataset = project.version(args.version).download(args.format)
    except Exception as exc:
        print(f"ERROR при завантаженні: {exc}")
        return 1
    finally:
        os.chdir(cwd)

    location = Path(dataset.location).resolve()
    data_yaml = location / "data.yaml"

    print()
    print("=" * 64)
    print(f"  Датасет:   {location}")
    print(f"  data.yaml: {data_yaml}")
    if data_yaml.exists():
        print(f"  ✓ data.yaml знайдено")
    else:
        print(f"  ⚠ data.yaml не знайдено — структура датасету нестандартна,")
        print(f"    перевір вміст папки вище")
    print("=" * 64)
    print()
    print("Запусти тренування:")
    print(f'  python scripts/train_weapon_model.py "{data_yaml}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
