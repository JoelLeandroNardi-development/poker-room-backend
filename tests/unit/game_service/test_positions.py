from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("GAME_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")

@pytest.fixture(scope="module")
def game_cmd_module():
    return load_service_app_module(
        "game-service", "application/commands/game_command_service",
        package_name="game_pos_test_app",
        reload_modules=True,
    )

@pytest.fixture(scope="module")
def cmd_service_class(game_cmd_module):
    return game_cmd_module.GameCommandService

@pytest.mark.unit
class TestAssignPositions:
    def test_two_players_dealer_is_small_blind(self, cmd_service_class):
        seats = [1, 2]
        dealer, sb, bb = cmd_service_class._assign_positions(seats, starting_dealer=1)
        assert dealer == 1
        assert sb == 1
        assert bb == 2

    def test_two_players_starting_at_seat2(self, cmd_service_class):
        seats = [1, 2]
        dealer, sb, bb = cmd_service_class._assign_positions(seats, starting_dealer=2)
        assert dealer == 2
        assert sb == 2
        assert bb == 1

    def test_three_players(self, cmd_service_class):
        seats = [1, 2, 3]
        dealer, sb, bb = cmd_service_class._assign_positions(seats, starting_dealer=1)
        assert dealer == 1
        assert sb == 2
        assert bb == 3

    def test_three_players_wrap(self, cmd_service_class):
        seats = [1, 2, 3]
        dealer, sb, bb = cmd_service_class._assign_positions(seats, starting_dealer=3)
        assert dealer == 3
        assert sb == 1
        assert bb == 2

    def test_six_players(self, cmd_service_class):
        seats = [1, 2, 3, 4, 5, 6]
        dealer, sb, bb = cmd_service_class._assign_positions(seats, starting_dealer=4)
        assert dealer == 4
        assert sb == 5
        assert bb == 6

    def test_starting_dealer_not_in_seats_defaults(self, cmd_service_class):
        seats = [2, 4, 6]
        dealer, sb, bb = cmd_service_class._assign_positions(seats, starting_dealer=99)
        assert dealer == 2
        assert sb == 4
        assert bb == 6

@pytest.mark.unit
class TestRotatePositions:
    def test_basic_rotation(self, cmd_service_class):
        seats = [1, 2, 3]
        dealer, sb, bb = cmd_service_class._rotate_positions(seats, current_dealer=1)
        assert dealer == 2
        assert sb == 3
        assert bb == 1

    def test_rotation_wraps_around(self, cmd_service_class):
        seats = [1, 2, 3]
        dealer, sb, bb = cmd_service_class._rotate_positions(seats, current_dealer=3)
        assert dealer == 1
        assert sb == 2
        assert bb == 3

    def test_two_player_rotation(self, cmd_service_class):
        seats = [1, 2]
        dealer, sb, bb = cmd_service_class._rotate_positions(seats, current_dealer=1)
        assert dealer == 2
        assert sb == 2
        assert bb == 1

    def test_four_player_rotation(self, cmd_service_class):
        seats = [1, 3, 5, 7]
        dealer, sb, bb = cmd_service_class._rotate_positions(seats, current_dealer=3)
        assert dealer == 5
        assert sb == 7
        assert bb == 1

    def test_current_dealer_not_in_seats(self, cmd_service_class):
        seats = [2, 4, 6]
        dealer, sb, bb = cmd_service_class._rotate_positions(seats, current_dealer=99)
        assert dealer == 2
        assert sb == 4
        assert bb == 6

    def test_continuous_rotation_cycles(self, cmd_service_class):
        seats = [1, 2, 3]
        current = 1
        visited = []
        for _ in range(3):
            d, s, b = cmd_service_class._rotate_positions(seats, current)
            visited.append(d)
            current = d
        assert visited == [2, 3, 1]