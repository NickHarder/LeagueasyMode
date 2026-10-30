import pytest

from leagueasymode.inference.structure_names import (
    InhibitorName,
    TurretName,
    read_inhibitor_name,
    read_turret_name,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # As the feed named them in the owner's Swiftplay of 2026-10-29 04:00, each at the second
        # the match timeline has the same team's turret of that lane and tier fall.
        ("Turret_TChaos_L0_P3_511845594_0", TurretName("CHAOS", "bot", "outer")),
        ("Turret_TOrder_L1_P3_1242677625_0", TurretName("ORDER", "mid", "outer")),
        ("Turret_TChaos_L0_P2_528623213_0", TurretName("CHAOS", "bot", "inner")),
        ("Turret_TOrder_L2_P3_1509986696_0", TurretName("ORDER", "top", "outer")),
        ("Turret_TChaos_L0_P1_478290356_0", TurretName("CHAOS", "bot", "inhibitor")),
        ("Turret_TOrder_L1_P5_3625540808_0", TurretName("ORDER", "mid", "nexus")),
        ("Turret_TOrder_L1_P4_3675873665_0", TurretName("ORDER", "mid", "nexus")),
        # The older names, as the tests have long built them.
        ("Turret_T2_L_03_A", TurretName("CHAOS", "top", "outer")),
        ("Turret_T1_C_01_A", TurretName("ORDER", "mid", "nexus")),
        ("Turret_T1_C_06_A", None),
        ("Turret_TNeutral_L0_P3_1_0", None),
        (None, None),
    ],
)
def test_a_turrets_name_says_whose_it_is_its_lane_and_its_tier(
    name: str | None, expected: TurretName | None
) -> None:
    assert read_turret_name(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # The Swiftplay's three: the timeline has mid, then bot, then top fall.
        ("Inhib_TOrder_L1_P1_2786523670_0", InhibitorName("ORDER", "mid")),
        ("Inhib_TOrder_L0_P1_2971077479_0", InhibitorName("ORDER", "bot")),
        ("Inhib_TOrder_L2_P1_2669080337_0", InhibitorName("ORDER", "top")),
        # ARAM's, in its one lane.
        ("Inhib_TChaos_L1_P1_2432143522_0", InhibitorName("CHAOS", "mid")),
        ("Barracks_T2_L1", InhibitorName("CHAOS", "top")),
        ("Barracks_Something_New", None),
    ],
)
def test_an_inhibitors_name_says_whose_it_is_and_its_lane(
    name: str, expected: InhibitorName | None
) -> None:
    assert read_inhibitor_name(name) == expected
