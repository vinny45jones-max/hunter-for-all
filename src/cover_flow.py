"""
Модуль cover_flow — управление процессом сопроводительного письма.

- Извлечение требований работодателя из описания вакансии
- Управление состоянием apply_state (idle → previewing → editing → sending → sent)
- Формирование превью письма с требованиями
- Генерация и перегенерация вариантов письма
"""

import json
import re
from typing import List, Optional

from src import ai_filter, database
from src.models import Vacancy


# Паттерны: триггерная фраза + захват требования до конца предложения.
# Группа 1 захватывает текст требования после триггера.
_TRIGGER_PATTERNS = [
    # "в сопроводительном письме укажите / напишите / расскажите ..."
    r"в\s+сопроводительном(?:\s+письме)?\s+(.{10,200})",
    # "в отклике укажите / напишите ..."
    r"в\s+отклике\s+(.{10,200})",
    # "в письме укажите / напишите / расскажите ..."
    r"в\s+письме\s+(.{10,200})",
    # "при отклике укажите / расскажите ..."
    r"при\s+отклике\s+(.{10,200})",
    # "ответьте на вопрос: ..."
    r"ответьте\s+на\s+вопрос[:\s]+(.{10,200})",
    # "обязательно укажите ..."
    r"обязательно\s+укажите\s+(.{10,200})",
    # "просим указать / написать ..."
    r"просим\s+(?:указать|написать|рассказать)\s+(.{10,200})",
    # "напишите в отклике ..."
    r"напишите\s+в\s+отклике\s+(.{10,200})",
    # "расскажите в письме / в отклике ..."
    r"расскажите\s+(?:в\s+(?:письме|отклике)\s+)?(.{10,200})",
    # "укажите в сопроводительном / в письме / в отклике ..."
    r"укажите\s+в\s+(?:сопроводительном|письме|отклике)\s+(.{10,200})",
]

# Компилируем один раз при импорте — IGNORECASE для заглавных букв в начале предложения
_COMPILED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in _TRIGGER_PATTERNS
]

# Ограничители: обрезаем захваченный текст по концу предложения/абзаца
_SENTENCE_END = re.compile(r"[.!?\n]")

_MAX_REQUIREMENTS = 5


def _trim_to_sentence(text: str) -> str:
    """Обрезает захваченный фрагмент до конца первого предложения."""
    text = text.strip()
    m = _SENTENCE_END.search(text)
    if m:
        text = text[: m.start() + 1]
    # Убрать хвостовые пробелы и незакрытую пунктуацию
    return text.strip().rstrip(",;:-–—")


def _normalize(text: str) -> str:
    """Нормализует пробелы и приводит к нижнему регистру для дедупликации."""
    return re.sub(r"\s+", " ", text.strip().lower())


def extract_cover_letter_requirements(description: str) -> List[str]:
    """
    Анализирует описание вакансии и извлекает требования работодателя
    к сопроводительному письму.

    Args:
        description: Текст описания вакансии (plain text из скрапера).

    Returns:
        Список конкретных требований (1-5 штук) или пустой список.
    """
    if not description:
        return []

    results: List[str] = []
    seen: set = set()

    for pattern in _COMPILED_PATTERNS:
        for match in pattern.finditer(description):
            raw = match.group(1)
            trimmed = _trim_to_sentence(raw)

            # Пропуск слишком коротких или бессмысленных захватов
            if len(trimmed) < 10:
                continue

            norm = _normalize(trimmed)
            if norm in seen:
                continue
            seen.add(norm)

            results.append(trimmed)

            if len(results) >= _MAX_REQUIREMENTS:
                return results

    return results


# ── Управление состоянием ────────────────────────────────────────────

# Допустимые переходы apply_state
_TRANSITIONS = {
    "idle": {"previewing"},
    "previewing": {"editing", "sending", "idle"},
    "editing": {"previewing", "idle"},
    "sending": {"sent", "failed"},
    "sent": set(),
    "failed": {"previewing", "idle"},
}


async def _set_state(vacancy_id: int, new_state: str, **kwargs) -> None:
    """Обновить apply_state в БД с проверкой допустимости перехода."""
    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy:
        raise ValueError(f"Вакансия {vacancy_id} не найдена")

    current = vacancy.apply_state
    allowed = _TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise ValueError(
            f"Недопустимый переход: {current} → {new_state} "
            f"(допустимо: {allowed})"
        )

    await database.update_apply_state(vacancy_id, new_state, **kwargs)


def _parse_requirements(vacancy: Vacancy) -> List[str]:
    """Получить requirements из JSON-поля или пустой список."""
    if not vacancy.employer_requirements:
        return []
    try:
        return json.loads(vacancy.employer_requirements)
    except (json.JSONDecodeError, TypeError):
        return []


# ── Основные операции ────────────────────────────────────────────────

async def start_cover_letter(vacancy_id: int) -> dict:
    """
    Начать процесс: извлечь требования, сгенерировать письмо, перейти в previewing.

    Returns:
        {
            "cover_letter": str,
            "requirements": list[str],
            "version": int,
            "require_cover_letter": bool,
        }
    """
    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy:
        raise ValueError(f"Вакансия {vacancy_id} не найдена")

    # Извлечь требования из описания (если ещё не сохранены)
    requirements = _parse_requirements(vacancy)
    if not requirements and vacancy.description:
        requirements = extract_cover_letter_requirements(vacancy.description)
        if requirements:
            await database.update_apply_state(
                vacancy_id,
                vacancy.apply_state,
                employer_requirements=json.dumps(requirements, ensure_ascii=False),
                require_cover_letter=1 if requirements else 0,
            )

    # Генерация письма
    version = await database.increment_cover_letter_version(vacancy_id)
    letter = await ai_filter.generate_cover_letter(
        vacancy, requirements=requirements, version=version
    )

    # Сохранить письмо и перейти в previewing
    await database.update_apply_state(
        vacancy_id, "previewing", cover_letter=letter
    )

    return {
        "cover_letter": letter,
        "requirements": requirements,
        "version": version,
        "require_cover_letter": bool(requirements),
    }


async def regenerate_cover_letter(vacancy_id: int) -> dict:
    """Сгенерировать новый вариант письма (другой ракурс)."""
    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy:
        raise ValueError(f"Вакансия {vacancy_id} не найдена")

    requirements = _parse_requirements(vacancy)
    version = await database.increment_cover_letter_version(vacancy_id)

    letter = await ai_filter.generate_cover_letter(
        vacancy, requirements=requirements, version=version
    )
    await database.update_apply_state(
        vacancy_id, "previewing", cover_letter=letter
    )

    return {
        "cover_letter": letter,
        "requirements": requirements,
        "version": version,
    }


async def enter_editing(vacancy_id: int) -> None:
    """Перейти в режим редактирования (пользователь пишет своё письмо)."""
    await _set_state(vacancy_id, "editing")


async def submit_user_text(vacancy_id: int, text: str) -> dict:
    """
    Пользователь прислал свой текст — сохранить и вернуть в превью.

    Returns:
        {"cover_letter": str, "version": int}
    """
    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy:
        raise ValueError(f"Вакансия {vacancy_id} не найдена")

    await database.update_apply_state(
        vacancy_id, "previewing", cover_letter=text
    )
    return {"cover_letter": text, "version": vacancy.cover_letter_version}


async def ai_improve_user_text(vacancy_id: int) -> dict:
    """
    AI-доработка текущего письма с учётом требований работодателя.

    Returns:
        {"cover_letter": str, "version": int}
    """
    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy or not vacancy.cover_letter:
        raise ValueError(f"Вакансия {vacancy_id}: нет текста для доработки")

    requirements = _parse_requirements(vacancy)
    improved = await ai_filter.improve_cover_letter(
        vacancy.cover_letter, vacancy, requirements=requirements
    )

    await database.update_apply_state(
        vacancy_id, "previewing", cover_letter=improved
    )
    return {"cover_letter": improved, "version": vacancy.cover_letter_version}


async def confirm_send(vacancy_id: int) -> None:
    """Подтвердить отправку — перейти в sending."""
    await _set_state(vacancy_id, "sending")


async def mark_sent(vacancy_id: int, negotiation_id: Optional[str] = None) -> None:
    """Отметить успешную отправку."""
    kwargs = {}
    if negotiation_id:
        kwargs["negotiation_id"] = negotiation_id
    await _set_state(vacancy_id, "sent", **kwargs)


async def mark_failed(vacancy_id: int) -> None:
    """Отметить неудачную отправку."""
    await _set_state(vacancy_id, "failed")


async def cancel(vacancy_id: int) -> None:
    """Отменить процесс — вернуться в idle."""
    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy:
        return
    if vacancy.apply_state in ("previewing", "editing", "failed"):
        await database.update_apply_state(vacancy_id, "idle")


def format_preview(cover_letter: str, requirements: List[str], version: int) -> str:
    """Сформировать текст превью письма для Telegram."""
    parts = []

    if requirements:
        parts.append("📋 <b>Требования работодателя:</b>")
        for i, req in enumerate(requirements, 1):
            parts.append(f"  {i}. {req}")
        parts.append("")

    parts.append(f"✉️ <b>Сопроводительное письмо (v{version}):</b>")
    parts.append(cover_letter)

    return "\n".join(parts)
