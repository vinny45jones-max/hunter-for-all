"""
Загрузка сессии rabota.by в Railway Volume.

Запускать ПОСЛЕ деплоя на Railway, когда Volume уже подключен:
    railway run python scripts/upload_session.py

Скрипт скопирует локальный data/rabota_session.json в /data/ внутри контейнера.
"""
import shutil
import os

SRC = "data/rabota_session.json"
DST = "/data/rabota_session.json"

if not os.path.exists(SRC):
    print(f"Файл {SRC} не найден. Сначала запусти save_cookies.py")
    exit(1)

os.makedirs("/data", exist_ok=True)
shutil.copy2(SRC, DST)
print(f"Сессия скопирована: {SRC} -> {DST}")
