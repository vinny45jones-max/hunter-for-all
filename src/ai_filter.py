import json
import re
from typing import List

import anthropic

from src.config import settings, log
from src.models import Vacancy, Message

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = (
    "Ты -- рекрутер-аналитик. Оцениваешь релевантность вакансии для кандидата. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-блоков."
)

EVALUATE_PROMPT = """
ПРОФИЛЬ КАНДИДАТА — Роман Комолов:
- Director of Business Development | Commercial Transformation & AI Integration Specialist
- 15+ лет управленческого опыта на позициях CEO, COO, CCO, коммерческий директор
- Отрасли: B2B оптовая торговля, дистрибуция, производство, ритейл, e-commerce, текстиль, бытовая техника
- Масштаб управления: компании с оборотом $2M—$60M, команды 25—150 чел
- Ключевые компетенции:
  * Business Development & Commercial Transformation
  * Operating Model Design & Process Optimization
  * P&L management, Margin Management, Category Management
  * KPI Systems, управленческий учет, финансовая аналитика
  * Inventory Optimization, Working Capital Management
  * CRM внедрение (Bitrix24), Change Management
- AI & Digital Transformation:
  * AI-Agent Orchestration (экосистемы из 10+ AI-агентов)
  * Автоматизация 25%+ критических бизнес-процессов
  * AI-Assisted Reporting & Decision Support Systems
  * Стек: n8n, Claude API, Supabase, Telegram-боты
- Подтверждённые результаты:
  * +25-40% рост валовой прибыли, +20% рост чистой прибыли
  * Экспортные контракты на $15M, запуск 6 направлений с нуля
  * Рост выручки компаний в 3-4 раза
  * $60M годовой оборот (собственный бизнес)
- Образование: MBA (РАНХиГС), БГУ (бухучёт, аудит)
- Языки: русский (родной), английский (C1-C2), польский (свободно)
- Локация: Минск, Беларусь | Варшава, Польша

ВАКАНСИЯ:
Название: {title}
Компания: {company}
Зарплата: {salary}
Город: {city}
Описание: {description}

ОЦЕНИ:
1. score (0-100) -- насколько вакансия подходит кандидату
2. reason -- почему, 1-2 предложения

JSON: {{"score": <int>, "reason": "<str>"}}
"""

COVER_LETTER_PROMPT = """
Напиши сопроводительное письмо (3-5 предложений) для отклика на вакансию.

Вакансия: {title} в {company}
Описание: {description}

Кандидат — Роман Комолов:
- 15+ лет на позициях CEO, COO, коммерческий директор в B2B, дистрибуции, ритейле, e-commerce
- Управлял компаниями с оборотом до $60M и командами до 150 человек
- Специализация: коммерческая трансформация, построение управляемых бизнес-систем
- AI-интегратор: создал экосистему из 10+ AI-агентов, автоматизировал 25%+ процессов
- Подтверждённые результаты: +25-40% рост валовой прибыли, экспортные контракты на $15M
- Стек: n8n, Claude API, Supabase, Bitrix24

Тон: уверенный, конкретный, без воды. Русский язык.
Не начинай с "Уважаемый". Сразу к делу.
Покажи конкретную ценность для этой компании, привяжи к их задачам.
"""

REPLY_PROMPT = """
Ты помогаешь соискателю ответить на сообщение работодателя.

ВАКАНСИЯ: {vacancy_title} в {company}
ОПИСАНИЕ ВАКАНСИИ: {vacancy_description}

ИСТОРИЯ ПЕРЕПИСКИ:
{conversation_history}

ПОСЛЕДНЕЕ СООБЩЕНИЕ ОТ РАБОТОДАТЕЛЯ:
{last_message}

ПРОФИЛЬ СОИСКАТЕЛЯ — Роман Комолов:
- 15+ лет C-level (CEO, COO, CCO) в B2B, дистрибуции, ритейле, e-commerce
- Коммерческая трансформация, AI-интеграция, автоматизация бизнес-процессов
- Управлял компаниями $2M—$60M, командами 25—150 чел
- Уверенный, конкретный стиль общения

ЗАДАЧА:
Напиши ответ (2-5 предложений).
- Если приглашают на собеседование — подтверди готовность, уточни формат
- Если задают вопрос — ответь по существу
- Если просят информацию — предоставь кратко
Тон: профессиональный, без подобострастия. Русский язык.
"""


def _parse_json(text: str) -> dict:
    # Убрать markdown-обёртку если есть
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: regex
    score_match = re.search(r'"score"\s*:\s*(\d+)', text)
    reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', text)
    if score_match:
        return {
            "score": int(score_match.group(1)),
            "reason": reason_match.group(1) if reason_match else "N/A",
        }
    raise ValueError(f"Cannot parse JSON from: {text[:200]}")


async def evaluate_relevance(vacancy: Vacancy) -> dict:
    prompt = EVALUATE_PROMPT.format(
        title=vacancy.title,
        company=vacancy.company or "Не указана",
        salary=vacancy.salary or "Не указана",
        city=vacancy.city or "Не указан",
        description=(vacancy.description or "")[:3000],
    )

    for attempt in range(2):
        try:
            response = await _client.messages.create(
                model=MODEL,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            result = _parse_json(text)
            result["score"] = max(0, min(100, int(result.get("score", 0))))
            return result
        except Exception as e:
            log.warning(f"AI evaluate attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue
            return {"score": 0, "reason": f"AI error: {e}"}


async def generate_cover_letter(vacancy: Vacancy) -> str:
    prompt = COVER_LETTER_PROMPT.format(
        title=vacancy.title,
        company=vacancy.company or "Не указана",
        description=(vacancy.description or "")[:3000],
    )

    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Cover letter generation failed: {e}")
        return ""


async def generate_reply(
    vacancy: Vacancy,
    history: List[Message],
) -> str:
    history_text = "\n".join(
        f"{'[Работодатель]' if m.direction == 'incoming' else '[Вы]'}: {m.text}"
        for m in history
    )
    last_incoming = next(
        (m.text for m in reversed(history) if m.direction == "incoming"), ""
    )

    prompt = REPLY_PROMPT.format(
        vacancy_title=vacancy.title if vacancy else "Не указана",
        company=vacancy.company if vacancy else "Не указана",
        vacancy_description=(vacancy.description or "")[:2000] if vacancy else "",
        conversation_history=history_text or "Нет истории",
        last_message=last_incoming or "Нет сообщения",
    )

    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Reply generation failed: {e}")
        return ""


async def improve_text(text: str) -> str:
    prompt = (
        f"Улучши этот текст ответа работодателю. "
        f"Сделай профессиональнее, конкретнее, убери воду. "
        f"Русский язык. Верни ТОЛЬКО текст ответа.\n\n{text}"
    )
    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Text improvement failed: {e}")
        return text
