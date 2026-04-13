"""Тесты для cover_flow: извлечение требований + state machine + format_preview."""

from unittest.mock import AsyncMock, patch

import pytest
from src.cover_flow import (
    _TRANSITIONS,
    _set_state,
    cancel,
    confirm_send,
    enter_editing,
    extract_cover_letter_requirements,
    format_preview,
    mark_failed,
    mark_sent,
    start_cover_letter,
    submit_user_text,
)
from src.models import Vacancy


class TestExtractRequirements:
    """Извлечение требований к сопроводительному письму из описания."""

    def test_empty_description(self):
        assert extract_cover_letter_requirements("") == []
        assert extract_cover_letter_requirements(None) == []

    def test_no_requirements(self):
        desc = "Ищем Python-разработчика. Опыт от 3 лет. Знание SQL."
        assert extract_cover_letter_requirements(desc) == []

    def test_v_sopr_pisme(self):
        desc = "В сопроводительном письме укажите ваш опыт работы с Python и ожидания по зарплате."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1
        assert "опыт работы с Python" in result[0].lower() or "python" in result[0].lower()

    def test_v_otklice(self):
        desc = "В отклике укажите ссылку на портфолио и примеры работ."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1
        assert "портфолио" in result[0].lower()

    def test_pri_otklice(self):
        desc = "При отклике расскажите почему вас заинтересовала эта позиция."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1

    def test_otvetye_na_vopros(self):
        desc = "Ответьте на вопрос: какой ваш самый сложный проект за последний год?"
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1
        assert "сложный проект" in result[0].lower()

    def test_obyazatelno_ukazhite(self):
        desc = "Обязательно укажите ваши зарплатные ожидания в белорусских рублях."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1
        assert "зарплатн" in result[0].lower()

    def test_prosim_ukazat(self):
        desc = "Просим указать опыт работы с микросервисной архитектурой."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1

    def test_multiple_requirements(self):
        desc = (
            "В сопроводительном письме укажите ваш опыт работы с Python. "
            "Обязательно укажите ожидания по зарплате в белорусских рублях. "
            "В отклике укажите ссылку на ваш GitHub профиль."
        )
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 2

    def test_max_five_requirements(self):
        parts = [
            "В сопроводительном письме укажите ваш опыт работы с базами данных.",
            "Обязательно укажите уровень владения английским языком.",
            "В отклике укажите ссылку на портфолио проектов.",
            "Просим указать опыт работы в распределённой команде.",
            "При отклике расскажите о вашем самом интересном проекте.",
            "Ответьте на вопрос: почему вы хотите работать у нас в компании?",
        ]
        desc = " ".join(parts)
        result = extract_cover_letter_requirements(desc)
        assert len(result) <= 5

    def test_deduplication(self):
        desc = (
            "В сопроводительном письме укажите ваш опыт работы с Python. "
            "В письме укажите ваш опыт работы с Python."
        )
        result = extract_cover_letter_requirements(desc)
        assert len(result) == 1

    def test_case_insensitive(self):
        desc = "В СОПРОВОДИТЕЛЬНОМ ПИСЬМЕ УКАЖИТЕ ваш опыт работы с Django фреймворком."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1

    def test_short_capture_skipped(self):
        """Паттерн .{10,200} не матчит захват короче 10 символов."""
        # "в отклике " + всего 5 символов — паттерн не сработает
        desc = "в отклике кратк"
        result = extract_cover_letter_requirements(desc)
        assert len(result) == 0

    def test_trim_to_sentence(self):
        desc = "В сопроводительном письме укажите ваш опыт работы с Python. Мы предлагаем конкурентную зарплату."
        result = extract_cover_letter_requirements(desc)
        assert len(result) >= 1
        assert "конкурентную" not in result[0].lower()


# ── Тесты state machine ────────────────────────────────────────────────


def _make_vacancy(apply_state="idle", **kwargs):
    """Фабрика Vacancy для тестов."""
    defaults = dict(
        id=1,
        external_id="v-100",
        url="https://rabota.by/vacancy/100",
        title="Python Dev",
        apply_state=apply_state,
        cover_letter_version=0,
    )
    defaults.update(kwargs)
    return Vacancy(**defaults)


class TestTransitionsTable:
    """Проверяем таблицу допустимых переходов."""

    def test_idle_can_go_to_previewing(self):
        assert "previewing" in _TRANSITIONS["idle"]

    def test_idle_cannot_go_to_sent(self):
        assert "sent" not in _TRANSITIONS["idle"]

    def test_previewing_can_go_to_editing_sending_idle(self):
        assert _TRANSITIONS["previewing"] == {"editing", "sending", "idle"}

    def test_editing_can_go_to_previewing_or_idle(self):
        assert _TRANSITIONS["editing"] == {"previewing", "idle"}

    def test_sending_can_go_to_sent_or_failed(self):
        assert _TRANSITIONS["sending"] == {"sent", "failed"}

    def test_sent_is_terminal(self):
        assert _TRANSITIONS["sent"] == set()

    def test_failed_can_go_to_previewing_or_idle(self):
        assert _TRANSITIONS["failed"] == {"previewing", "idle"}


class TestSetState:
    """_set_state — проверяем валидацию переходов."""

    @pytest.mark.asyncio
    async def test_valid_transition(self):
        vac = _make_vacancy("idle")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await _set_state(1, "previewing")
            db.update_apply_state.assert_called_once_with(1, "previewing")

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self):
        vac = _make_vacancy("idle")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            with pytest.raises(ValueError, match="Недопустимый переход"):
                await _set_state(1, "sent")

    @pytest.mark.asyncio
    async def test_vacancy_not_found_raises(self):
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="не найдена"):
                await _set_state(1, "previewing")


class TestStartCoverLetter:
    """start_cover_letter — извлечение требований + генерация + переход."""

    @pytest.mark.asyncio
    async def test_generates_letter_and_transitions(self):
        vac = _make_vacancy(
            "idle", description="В сопроводительном письме укажите опыт работы с Python и Django."
        )
        with patch("src.cover_flow.database") as db, \
             patch("src.cover_flow.ai_filter") as ai:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            db.increment_cover_letter_version = AsyncMock(return_value=1)
            ai.generate_cover_letter = AsyncMock(return_value="Уважаемый работодатель...")

            result = await start_cover_letter(1)

            assert result["cover_letter"] == "Уважаемый работодатель..."
            assert result["version"] == 1
            assert result["require_cover_letter"] is True
            assert len(result["requirements"]) >= 1
            # Финальный вызов — переход в previewing
            last_call = db.update_apply_state.call_args_list[-1]
            assert last_call.args == (1, "previewing")

    @pytest.mark.asyncio
    async def test_vacancy_not_found(self):
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="не найдена"):
                await start_cover_letter(99)


class TestEnterEditing:
    @pytest.mark.asyncio
    async def test_previewing_to_editing(self):
        vac = _make_vacancy("previewing")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await enter_editing(1)
            db.update_apply_state.assert_called_once_with(1, "editing")


class TestSubmitUserText:
    @pytest.mark.asyncio
    async def test_saves_text_and_returns(self):
        vac = _make_vacancy("editing", cover_letter_version=2)
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            result = await submit_user_text(1, "Моё письмо")
            assert result["cover_letter"] == "Моё письмо"
            assert result["version"] == 2


class TestConfirmAndMark:
    @pytest.mark.asyncio
    async def test_confirm_send(self):
        vac = _make_vacancy("previewing")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await confirm_send(1)
            db.update_apply_state.assert_called_once_with(1, "sending")

    @pytest.mark.asyncio
    async def test_mark_sent(self):
        vac = _make_vacancy("sending")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await mark_sent(1, negotiation_id="neg-42")
            db.update_apply_state.assert_called_once_with(
                1, "sent", negotiation_id="neg-42"
            )

    @pytest.mark.asyncio
    async def test_mark_failed(self):
        vac = _make_vacancy("sending")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await mark_failed(1)
            db.update_apply_state.assert_called_once_with(1, "failed")


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_from_previewing(self):
        vac = _make_vacancy("previewing")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await cancel(1)
            db.update_apply_state.assert_called_once_with(1, "idle")

    @pytest.mark.asyncio
    async def test_cancel_from_editing(self):
        vac = _make_vacancy("editing")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await cancel(1)
            db.update_apply_state.assert_called_once_with(1, "idle")

    @pytest.mark.asyncio
    async def test_cancel_from_sent_does_nothing(self):
        vac = _make_vacancy("sent")
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=vac)
            db.update_apply_state = AsyncMock()
            await cancel(1)
            db.update_apply_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_vacancy_not_found(self):
        with patch("src.cover_flow.database") as db:
            db.get_vacancy = AsyncMock(return_value=None)
            db.update_apply_state = AsyncMock()
            await cancel(99)  # не должен упасть
            db.update_apply_state.assert_not_called()


class TestFormatPreview:
    def test_with_requirements(self):
        text = format_preview("Письмо", ["Опыт Python", "Зарплата"], 1)
        assert "Требования работодателя" in text
        assert "1. Опыт Python" in text
        assert "2. Зарплата" in text
        assert "Письмо" in text
        assert "v1" in text

    def test_without_requirements(self):
        text = format_preview("Письмо", [], 3)
        assert "Требования" not in text
        assert "Письмо" in text
        assert "v3" in text

    def test_version_displayed(self):
        text = format_preview("X", [], 5)
        assert "v5" in text
