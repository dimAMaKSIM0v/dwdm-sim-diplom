#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Точка входа в приложение для моделирования DWDM сетей
"""
import argparse
import sys
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

