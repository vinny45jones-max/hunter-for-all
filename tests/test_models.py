"""
Тест 2: dataclass модели создаются корректно.
"""
import pytest
from src.models import Vacancy, Message, Conversation


class TestVacancy:
    def test_create_minimal(self):
        v = Vacancy(external_id="123", url="https://example.com", title="CEO")
        assert v.external_id == "123"
        assert v.status == "new"
        assert v.relevance_score == 0

    def test_create_full(self):
        v = Vacancy(
            external_id="456",
            url="https://example.com/456",
            title="CTO",
            company="Acme",
            salary="5000 USD",
            city="Minsk",
            description="Long description",
            relevance_score=85,
            relevance_reason="Great match",
            cover_letter="Dear Sir...",
            status="filtered",
            id=1,
        )
        assert v.company == "Acme"
        assert v.relevance_score == 85
        assert v.id == 1

    def test_defaults(self):
        v = Vacancy(external_id="x", url="u", title="t")
        assert v.company is None
        assert v.salary is None
        assert v.city is None
        assert v.description is None
        assert v.cover_letter is None
        assert v.relevance_reason is None
        assert v.id is None


class TestMessage:
    def test_create_incoming(self):
        m = Message(
            message_id="msg1",
            text="Hello",
            direction="incoming",
            sender="HR",
            company="Acme",
        )
        assert m.direction == "incoming"
        assert m.is_read is False
        assert m.replied is False

    def test_create_outgoing(self):
        m = Message(
            message_id="msg2",
            text="Thanks!",
            direction="outgoing",
        )
        assert m.direction == "outgoing"
        assert m.sender is None


class TestConversation:
    def test_create(self):
        c = Conversation(
            conversation_id="conv1",
            vacancy_title="CEO",
            company="Acme",
            status="active",
        )
        assert c.conversation_id == "conv1"
        assert c.status == "active"
        assert c.vacancy_id is None
        assert c.last_message_at is None
