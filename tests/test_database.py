"""
Тест 3: все CRUD операции базы данных.
Каждый тест получает чистую in-memory-like БД через фикстуру init_db.
"""
import pytest
from src.models import Vacancy, Message, Conversation
from src import database


pytestmark = pytest.mark.asyncio


# ── Vacancies ──────────────────────────────────────


async def test_save_and_get_vacancy(init_db):
    v = Vacancy(external_id="v1", url="https://r.by/1", title="CEO", company="Acme")
    vid = await database.save_vacancy(v)
    assert vid > 0

    fetched = await database.get_vacancy(vid)
    assert fetched is not None
    assert fetched.title == "CEO"
    assert fetched.company == "Acme"


async def test_save_vacancy_upsert(init_db):
    v1 = Vacancy(external_id="v2", url="https://r.by/2", title="CTO", relevance_score=50)
    await database.save_vacancy(v1)

    v2 = Vacancy(external_id="v2", url="https://r.by/2", title="CTO", relevance_score=90)
    await database.save_vacancy(v2)

    # Должна быть 1 запись с обновлённым score
    last = await database.get_last_vacancies(10)
    cto_list = [x for x in last if x.external_id == "v2"]
    assert len(cto_list) == 1
    assert cto_list[0].relevance_score == 90


async def test_filter_new(init_db):
    existing = Vacancy(external_id="old1", url="u", title="Old")
    await database.save_vacancy(existing)

    candidates = [
        Vacancy(external_id="old1", url="u", title="Old"),
        Vacancy(external_id="new1", url="u2", title="New"),
    ]
    result = await database.filter_new(candidates)
    assert len(result) == 1
    assert result[0].external_id == "new1"


async def test_filter_new_empty(init_db):
    result = await database.filter_new([])
    assert result == []


async def test_update_status(init_db):
    v = Vacancy(external_id="s1", url="u", title="T")
    vid = await database.save_vacancy(v)

    await database.update_status(vid, "applied")
    fetched = await database.get_vacancy(vid)
    assert fetched.status == "applied"


async def test_update_status_with_error(init_db):
    v = Vacancy(external_id="e1", url="u", title="T")
    vid = await database.save_vacancy(v)

    await database.update_status(vid, "error", "Captcha detected")
    fetched = await database.get_vacancy(vid)
    assert fetched.status == "error"


async def test_get_last_vacancies(init_db):
    for i in range(7):
        await database.save_vacancy(
            Vacancy(external_id=f"l{i}", url=f"u{i}", title=f"T{i}")
        )
    last5 = await database.get_last_vacancies(5)
    assert len(last5) == 5
    # Последние должны идти первыми (ORDER BY id DESC)
    assert last5[0].external_id == "l6"


async def test_get_stats(init_db):
    await database.save_vacancy(
        Vacancy(external_id="st1", url="u", title="T", status="sent_to_tg")
    )
    await database.save_vacancy(
        Vacancy(external_id="st2", url="u2", title="T2", status="new")
    )
    stats = await database.get_stats()
    assert stats["total"] == 2
    assert stats["sent_to_tg"] == 1
    assert stats["applied"] == 0


async def test_save_search_log(init_db):
    # Просто не должен упасть
    await database.save_search_log("CEO,CTO", total=100, new=10, relevant=3)


async def test_count_today_applies(init_db):
    count = await database.count_today_applies()
    assert count == 0


# ── Messages / Conversations ──────────────────────


async def test_save_conversation(init_db):
    c = Conversation(
        conversation_id="c1",
        vacancy_title="CEO",
        company="Acme",
        status="active",
    )
    cid = await database.save_conversation(c)
    assert cid > 0

    fetched = await database.get_conversation("c1")
    assert fetched is not None
    assert fetched.company == "Acme"


async def test_save_incoming_message(init_db):
    msg = Message(
        message_id="m1",
        text="Приглашаем на собеседование",
        direction="incoming",
        sender="HR",
        company="Acme",
        conversation_id="c1",
    )
    mid = await database.save_incoming_message(msg)
    assert mid is not None

    # Дубликат
    dup = await database.save_incoming_message(msg)
    assert dup is None


async def test_save_outgoing_message(init_db):
    # Создать conversation
    c = Conversation(conversation_id="c2", company="Test", status="active")
    await database.save_conversation(c)

    await database.save_outgoing_message("c2", "Спасибо, готов!")

    history = await database.get_conversation_history("c2")
    assert len(history) == 1
    assert history[0].direction == "outgoing"
    assert "Спасибо" in history[0].text

    # Conversation status -> replied
    conv = await database.get_conversation("c2")
    assert conv.status == "replied"


async def test_get_unread_messages(init_db):
    msg = Message(
        message_id="unread1",
        text="Hello",
        direction="incoming",
        company="Test",
    )
    await database.save_incoming_message(msg)

    unread = await database.get_unread_messages()
    assert len(unread) >= 1
    assert any(m.message_id == "unread1" for m in unread)


async def test_get_active_conversations(init_db):
    c1 = Conversation(conversation_id="a1", company="A", status="active")
    c2 = Conversation(conversation_id="a2", company="B", status="closed")
    await database.save_conversation(c1)
    await database.save_conversation(c2)

    active = await database.get_active_conversations()
    ids = [c.conversation_id for c in active]
    assert "a1" in ids
    assert "a2" not in ids  # closed не попадает


async def test_find_vacancy_by_company_title(init_db):
    v = Vacancy(
        external_id="f1", url="u", title="CEO",
        company="FindMe Corp", status="new",
    )
    await database.save_vacancy(v)

    found = await database.find_vacancy_by_company_title("FindMe Corp", "CEO")
    assert found is not None
    assert found.company == "FindMe Corp"

    not_found = await database.find_vacancy_by_company_title("NoSuch", "CEO")
    assert not_found is None


async def test_get_vacancy_by_conversation(init_db):
    # Нет vacancy_id — вернёт None
    c = Conversation(conversation_id="vbc1", company="X", status="active")
    await database.save_conversation(c)

    result = await database.get_vacancy_by_conversation("vbc1")
    assert result is None
