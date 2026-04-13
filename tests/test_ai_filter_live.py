import pytest

from src.models import Vacancy


pytestmark = [pytest.mark.asyncio, pytest.mark.live_api]


EXECUTIVE_VACANCY = Vacancy(
    external_id="live_exec_1",
    url="https://example.com/live/exec",
    title="Commercial Director / COO",
    company="B2B Distribution Group",
    salary="6000 USD",
    city="Minsk",
    description=(
        "We need an executive leader for a wholesale distribution business. "
        "Responsibilities include P&L ownership, sales management, KPI design, "
        "category management, CRM rollout, supplier negotiations, and process optimization "
        "for a 40-person team."
    ),
)

AI_TRANSFORMATION_VACANCY = Vacancy(
    external_id="live_exec_2",
    url="https://example.com/live/ai",
    title="Director of Business Development and AI Transformation",
    company="Digital Transformation Studio",
    salary="7000 USD",
    city="Minsk",
    description=(
        "Lead commercial growth, client strategy, and AI-driven process redesign for "
        "mid-market companies. Role includes executive stakeholder management, "
        "automation roadmap, delivery team leadership, and packaging AI products "
        "for business use cases."
    ),
)

FRONTEND_VACANCY = Vacancy(
    external_id="live_low_1",
    url="https://example.com/live/frontend",
    title="Frontend Engineer (React/TypeScript)",
    company="Product Engineering Team",
    salary="3500 USD",
    city="Minsk",
    description=(
        "Build UI features with React, TypeScript, GraphQL, design systems, and "
        "automated tests. Individual contributor role focused on frontend architecture, "
        "component development, and close collaboration with designers."
    ),
)


def _assert_valid_live_result(result: dict):
    assert isinstance(result, dict)
    assert isinstance(result.get("score"), int)
    assert 0 <= result["score"] <= 100

    reason = result.get("reason")
    assert isinstance(reason, str)
    assert reason.strip()
    assert not reason.startswith("AI error:")


async def test_live_relevance_scores_rank_executive_roles_above_frontend(
    live_anthropic_api_key,
):
    from src.ai_filter import evaluate_and_cover

    executive = await evaluate_and_cover(EXECUTIVE_VACANCY, min_score=60)
    ai_transformation = await evaluate_and_cover(AI_TRANSFORMATION_VACANCY, min_score=60)
    frontend = await evaluate_and_cover(FRONTEND_VACANCY, min_score=60)

    _assert_valid_live_result(executive)
    _assert_valid_live_result(ai_transformation)
    _assert_valid_live_result(frontend)

    assert executive["score"] > frontend["score"]
    assert ai_transformation["score"] > frontend["score"]

    # cover letter генерируется для релевантных в том же вызове
    assert executive.get("cover_letter")
    assert isinstance(executive["cover_letter"], str)
    assert len(executive["cover_letter"].strip()) >= 80
