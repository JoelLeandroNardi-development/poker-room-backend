"""Scenario-driven integration tests using the scenario runner framework.

Each test defines a full hand scenario declaratively and verifies the
outcome through the scenario runner DSL.
"""

from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def scenario_mod():
    return load_service_app_module(
        "game-service", "domain/scenario_runner",
        package_name="scenario_test_app", reload_modules=True,
    )

@pytest.fixture(scope="module")
def pipeline_mod():
    return load_service_app_module(
        "game-service", "domain/engine/action_pipeline",
        package_name="scenario_test_app",
    )

@pytest.fixture(scope="module")
def models_mod():
    return load_service_app_module(
        "game-service", "domain/models",
        package_name="scenario_test_app",
    )

@pytest.fixture
def HandScenario(scenario_mod):
    return scenario_mod.HandScenario

@pytest.fixture
def PlayerSetup(scenario_mod):
    return scenario_mod.PlayerSetup

@pytest.fixture
def BlindSetup(scenario_mod):
    return scenario_mod.BlindSetup

@pytest.fixture
def run_scenario(scenario_mod):
    return scenario_mod.run_scenario

@pytest.fixture
def apply_action(pipeline_mod):
    return pipeline_mod.apply_action

@pytest.fixture
def Round(models_mod):
    return models_mod.Round

@pytest.fixture
def RoundPlayer(models_mod):
    return models_mod.RoundPlayer

def _make_scenario(HandScenario, PlayerSetup, BlindSetup, name, players, blinds=(10, 20), dealer=1):
    return HandScenario(
        name=name,
        players=[PlayerSetup(p[0], p[1], p[2]) for p in players],
        blinds=BlindSetup(blinds[0], blinds[1]),
        dealer_seat=dealer,
    )

class TestHeadsUpScenarios:
    def test_heads_up_fold(self, run_scenario, apply_action, Round, RoundPlayer,
                           HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Heads-up fold",
            [("p1", 1, 1000), ("p2", 2, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p2", "FOLD", 0)
        scenario.expect_action_closed()
        scenario.expect_player_folded("p2")

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]
        assert result.actions_applied == 1

    def test_heads_up_call_check(self, run_scenario, apply_action, Round, RoundPlayer,
                                  HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Heads-up limp",
            [("p1", 1, 1000), ("p2", 2, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p2", "CALL", 0)
        scenario.add_action("p1", "CHECK", 0)
        scenario.expect_action_closed()
        scenario.expect_pot(40)

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]

class TestThreePlayerScenarios:
    def test_everyone_folds_to_bb(self, run_scenario, apply_action, Round, RoundPlayer,
                                   HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Fold to BB",
            [("p1", 1, 1000), ("p2", 2, 1000), ("p3", 3, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p1", "FOLD", 0)
        scenario.add_action("p2", "FOLD", 0)
        scenario.expect_action_closed()
        scenario.expect_player_folded("p1")
        scenario.expect_player_folded("p2")

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]

    def test_three_way_call(self, run_scenario, apply_action, Round, RoundPlayer,
                             HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Three-way limp",
            [("p1", 1, 1000), ("p2", 2, 1000), ("p3", 3, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p1", "CALL", 0)
        scenario.add_action("p2", "CALL", 0)
        scenario.add_action("p3", "CHECK", 0)
        scenario.expect_action_closed()
        scenario.expect_pot(60)

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]

    def test_raise_and_reraise(self, run_scenario, apply_action, Round, RoundPlayer,
                                HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "3-bet pot",
            [("p1", 1, 1000), ("p2", 2, 1000), ("p3", 3, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p1", "RAISE", 60)
        scenario.add_action("p2", "RAISE", 180)
        scenario.add_action("p3", "FOLD", 0)
        scenario.add_action("p1", "CALL", 0)
        scenario.add_action("p1", "CALL", 0)
        scenario.expect_action_closed()
        scenario.expect_player_folded("p3")

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]

class TestAllInScenarios:
    def test_short_stack_all_in(self, run_scenario, apply_action, Round, RoundPlayer,
                                 HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Short stack all-in",
            [("p1", 1, 50), ("p2", 2, 1000), ("p3", 3, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p1", "ALL_IN", 0)
        scenario.add_action("p2", "CALL", 0)
        scenario.add_action("p3", "CALL", 0)
        scenario.expect_action_closed()

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]

    def test_multi_all_in(self, run_scenario, apply_action, Round, RoundPlayer,
                           HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Double all-in",
            [("p1", 1, 100), ("p2", 2, 200), ("p3", 3, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p1", "ALL_IN", 0)
        scenario.add_action("p2", "ALL_IN", 0)
        scenario.add_action("p3", "CALL", 0)
        scenario.expect_action_closed()

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed, [f.message for f in result.failures]

class TestScenarioRunnerMeta:
    def test_expectation_failures_reported(self, run_scenario, apply_action, Round, RoundPlayer,
                                            HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "Wrong pot expectation",
            [("p1", 1, 1000), ("p2", 2, 1000)],
            blinds=(10, 20), dealer=1,
        )
        scenario.add_action("p1", "FOLD", 0)
        scenario.expect_pot(99999)

        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert not result.passed
        assert len(result.failures) == 1
        assert "99999" in result.failures[0].message

    def test_empty_scenario(self, run_scenario, apply_action, Round, RoundPlayer,
                             HandScenario, PlayerSetup, BlindSetup):
        scenario = _make_scenario(
            HandScenario, PlayerSetup, BlindSetup,
            "No-op",
            [("p1", 1, 1000), ("p2", 2, 1000)],
            blinds=(10, 20), dealer=1,
        )
        result = run_scenario(scenario, apply_action, Round, RoundPlayer)
        assert result.passed
        assert result.actions_applied == 0