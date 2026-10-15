from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from simile.schema import PLAYER_ID, Aspect, CoreValue, Npc
from simile.social import RelationshipConfig, meet

NPCS = Path(__file__).parents[1] / "fixtures" / "npcs"


def npc(name: str) -> Npc:
    return Npc.model_validate_json((NPCS / f"{name}.json").read_bytes())


def test_contrasting_personalities_meet_strangers_differently() -> None:
    warm = meet(npc("mei"), "suki")
    guarded = meet(npc("viktor"), "suki")

    assert warm.baseline.like > guarded.baseline.like
    assert warm.baseline.trust > guarded.baseline.trust


def test_a_new_relationship_starts_at_its_baseline_with_no_history() -> None:
    rel = meet(npc("viktor"), PLAYER_ID)

    assert (rel.owner, rel.about) == ("viktor", PLAYER_ID)
    assert (rel.like, rel.trust, rel.respect) == (
        rel.baseline.like,
        rel.baseline.trust,
        rel.baseline.respect,
    )
    assert rel.familiarity == 0
    assert rel.flags == []
    assert rel.last_interaction is None


def test_the_config_sets_the_weights() -> None:
    config = RelationshipConfig(baseline_weights={Aspect.LIKE: {CoreValue.CONNECTION: 1.0}})

    rel = meet(npc("mei"), "viktor", config=config)

    assert rel.baseline.like == pytest.approx(0.92)
    assert (rel.baseline.trust, rel.baseline.respect) == (0.5, 0.5)


def test_meet_rejects_meeting_yourself() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        meet(npc("mei"), "mei")


@given(
    st.lists(st.floats(0, 1), min_size=len(CoreValue), max_size=len(CoreValue)),
    st.dictionaries(
        st.sampled_from(Aspect),
        st.dictionaries(st.sampled_from(CoreValue), st.floats(-1, 1)),
    ),
)
def test_every_baseline_is_in_range(
    values: list[float], weights: dict[Aspect, dict[CoreValue, float]]
) -> None:
    owner = npc("mei").model_copy(update={"values": dict(zip(CoreValue, values, strict=True))})

    rel = meet(owner, "viktor", config=RelationshipConfig(baseline_weights=weights))

    assert all(0 <= score <= 1 for score in rel.baseline.model_dump().values())
