#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Точка входа в приложение для моделирования DWDM сетей
"""
import argparse
import os
import sys
import tempfile
from PyQt5.QtWidgets import QApplication
from core.models.network import Network
from gui.main_window import MainWindow
from utils.project_io import ProjectLoadError, load_network_from_json


def parse_args(argv: list[str]):
    """Парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(description="DWDM Network Simulator")
    parser.add_argument(
        "--project",
        type=str,
        default="",
        help="Путь к JSON-файлу схемы для загрузки при старте",
    )
    return parser.parse_args(argv[1:])


def main():
    """Главная функция запуска приложения."""
    args = parse_args(sys.argv)

    # QtWebEngine (Chromium) иногда падает, если нет прав на GPUCache в профиле.
    # Принудительно отключаем GPU и направляем кеш/профиль в доступную временную папку.
    os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --disable-gpu-compositing")
    webengine_profile_root = os.path.join(tempfile.gettempdir(), "dwdm_webengine")
    os.makedirs(webengine_profile_root, exist_ok=True)
    os.environ.setdefault("QTWEBENGINEPROFILE_DATA_PATH", webengine_profile_root)
    os.environ.setdefault("QTWEBENGINEPROFILE_CACHE_PATH", webengine_profile_root)

    app = QApplication(sys.argv)
    app.setApplicationName("DWDM Network Simulator")

    network = None
    if args.project:
        try:
            network = load_network_from_json(args.project)
            print(f"[INFO] Загружена схема из файла: {args.project}")
        except ProjectLoadError as exc:
            print(f"[ERROR] Не удалось загрузить схему из файла '{args.project}': {exc}", file=sys.stderr)
            print("[INFO] Приложение запущено с пустой схемой.", file=sys.stderr)
            network = Network()

    # Создаем и показываем главное окно
    window = MainWindow(network=network)
    window.show()

    # Запускаем цикл обработки событий
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

