"""
Тест 1: все модули проекта импортируются без ошибок.
Проверяет, что нет синтаксических ошибок и незакрытых зависимостей.
"""
import importlib
import pytest


MODULES = [
    "src.config",
    "src.models",
    "src.database",
    "src.ai_filter",
    "src.scraper",
    "src.bot",
    "src.applier",
    "src.inbox",
    "src.responder",
    "src.pipeline",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_import(module_name):
    mod = importlib.import_module(module_name)
    assert mod is not None
