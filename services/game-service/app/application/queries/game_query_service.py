from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import game_to_response, round_to_response, round_player_to_response
from ...domain.constants import BetAction, ErrorMessage, GameStatus, RoundStatus, Street
from ...domain.ledger.hand_history import build_hand_timeline
from ...domain.ledger.hand_ledger import LedgerRow
from ...domain.ledger.hand_replay import replay_hand, verify_consistency
from ...domain.models import Game, Round
from ...domain.schemas import (
    ConsistencyCheckResponse, GameResponse, LegalAction, PlayerSnapshotResponse, ReplayResponse,
    ReplayStepResponse, RoundResponse, SettlementExplanationResponse,TableStateResponse,
    TimelineResponse, TimelineStreetResponse, PotExplanation as PotExplanationSchema,
)
from ...domain.reporting.settlement_explainer import explain_settlement
from ...domain.engine.side_pots import PlayerContribution
from ...infrastructure.repository import (
    get_ledger_entries, get_rounds_for_game, get_active_round,
    get_round_players, get_round_payouts, fetch_or_raise,
)

class GameQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_game(self, game_id: str) -> GameResponse:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )
        return game_to_response(game)

    async def get_game_for_room(self, room_id: str) -> GameResponse | None:
        res = await self.db.execute(
            select(Game)
            .where(Game.room_id == room_id, Game.status == GameStatus.ACTIVE)
        )
        game = res.scalar_one_or_none()
        if game is None:
            return None
        return game_to_response(game)

    async def list_rounds(self, game_id: str) -> list[RoundResponse]:
        rounds = await get_rounds_for_game(self.db, game_id)
        result = []
        for r in rounds:
            players = await get_round_players(self.db, r.round_id)
            payouts = await get_round_payouts(self.db, r.round_id)
            result.append(round_to_response(r, players, payouts))
        return result

    async def get_round(self, round_id: str) -> RoundResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        players = await get_round_players(self.db, round_id)
        payouts = await get_round_payouts(self.db, round_id)
        return round_to_response(game_round, players, payouts)

    async def get_active_round(self, game_id: str) -> RoundResponse | None:
        game_round = await get_active_round(self.db, game_id)
        if game_round is None:
            return None
        players = await get_round_players(self.db, game_round.round_id)
        payouts = await get_round_payouts(self.db, game_round.round_id)
        return round_to_response(game_round, players, payouts)

    async def _ledger_rows(self, round_id: str) -> list[LedgerRow]:
        entries = await get_ledger_entries(self.db, round_id)
        return [
            LedgerRow(
                entry_id=e.entry_id,
                entry_type=e.entry_type,
                player_id=e.player_id,
                amount=e.amount,
                detail=e.detail,
                original_entry_id=e.original_entry_id,
            )
            for e in entries
        ]

    async def get_replay(self, round_id: str) -> ReplayResponse:
        await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        rows = await self._ledger_rows(round_id)
        result = replay_hand(rows)

        steps = [
            ReplayStepResponse(
                step_number=s.step_number,
                entry_id=s.entry_id,
                entry_type=s.entry_type,
                player_id=s.player_id,
                amount=s.amount,
                pot_total=s.state_after.pot_total,
                players=[
                    PlayerSnapshotResponse(
                        player_id=ps.player_id,
                        stack_adjustment=ps.stack_adjustment,
                        total_committed=ps.total_committed,
                        total_won=ps.total_won,
                    )
                    for ps in s.state_after.players.values()
                ],
            )
            for s in result.steps
        ]

        return ReplayResponse(
            round_id=round_id,
            entry_count=result.entry_count,
            is_consistent=result.is_consistent,
            steps=steps,
        )

    async def get_timeline(self, round_id: str) -> TimelineResponse:
        await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        rows = await self._ledger_rows(round_id)
        timeline = build_hand_timeline(round_id, rows)

        streets = [
            TimelineStreetResponse(
                name=s.street,
                actions=[
                    {
                        "entry_id": a.entry_id,
                        "player_id": a.player_id,
                        "action_type": a.action_type,
                        "amount": a.amount,
                        "pot_running_total": a.pot_running_total,
                    }
                    for a in s.actions
                ],
            )
            for s in timeline.streets
        ]

        payouts = [
            {"entry_id": p.entry_id, "player_id": p.player_id, "amount": p.amount}
            for p in timeline.payouts
        ]
        corrections = [
            {
                "entry_id": c.entry_id,
                "correction_type": c.correction_type,
                "player_id": c.player_id,
                "amount": c.amount,
                "original_entry_id": c.original_entry_id,
            }
            for c in timeline.corrections
        ]

        return TimelineResponse(
            round_id=round_id,
            streets=streets,
            payouts=payouts,
            corrections=corrections,
        )

    async def get_settlement_explanation(self, round_id: str) -> SettlementExplanationResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        round_players = await get_round_players(self.db, round_id)
        payouts = await get_round_payouts(self.db, round_id)

        contributions = [
            PlayerContribution(
                player_id=rp.player_id,
                committed_this_hand=rp.committed_this_hand,
                has_folded=rp.has_folded,
                reached_showdown=not rp.has_folded,
            )
            for rp in round_players
        ]

        submitted = {}
        for p in payouts:
            submitted.setdefault(p.pot_index, {
                "pot_index": p.pot_index,
                "winners": [],
            })
            submitted[p.pot_index]["winners"].append({
                "player_id": p.player_id,
                "amount": p.amount,
            })

        explanation = explain_settlement(
            contributions,
            list(submitted.values()) if submitted else None,
        )

        pots = [
            PotExplanationSchema(
                pot_index=pe.pot_index,
                pot_type=pe.pot_label,
                amount=pe.amount,
                contributors=list(pe.contributor_player_ids),
                winners=[
                    {"player_id": w.player_id, "amount": w.amount}
                    for w in pe.winners
                ],
            )
            for pe in explanation.pots
        ]

        return SettlementExplanationResponse(
            round_id=round_id,
            pots=pots,
            narrative=explanation.narrative,
        )

    async def check_consistency(self, round_id: str) -> ConsistencyCheckResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        round_players = await get_round_players(self.db, round_id)
        rows = await self._ledger_rows(round_id)

        live_committed = {rp.player_id: rp.committed_this_hand for rp in round_players}
        discrepancies = verify_consistency(rows, game_round.pot_amount, live_committed)

        return ConsistencyCheckResponse(
            round_id=round_id,
            is_consistent=len(discrepancies) == 0,
            discrepancies=discrepancies,
        )

    async def get_table_state(self, round_id: str) -> TableStateResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )
        round_players = await get_round_players(self.db, round_id)

        legal_actions: list[LegalAction] = []
        computed_call_amount: int | None = None
        if game_round.acting_player_id and not game_round.is_action_closed:
            acting_rp = next(
                (rp for rp in round_players if rp.player_id == game_round.acting_player_id),
                None,
            )
            if acting_rp:
                call_amount = max(0, game_round.current_highest_bet - acting_rp.committed_this_street)
                computed_call_amount = call_amount
                stack = acting_rp.stack_remaining

                legal_actions.append(LegalAction(action=BetAction.FOLD))

                if call_amount == 0:
                    legal_actions.append(LegalAction(action=BetAction.CHECK))
                else:
                    effective_call = min(call_amount, stack)
                    legal_actions.append(LegalAction(
                        action=BetAction.CALL, min_amount=effective_call, max_amount=effective_call,
                    ))

                if game_round.current_highest_bet == 0 and stack > 0:
                    legal_actions.append(LegalAction(
                        action=BetAction.BET,
                        min_amount=game_round.minimum_raise_amount,
                        max_amount=stack,
                    ))
                elif game_round.current_highest_bet > 0 and stack > call_amount:
                    min_raise_total = game_round.current_highest_bet + game_round.minimum_raise_amount
                    legal_actions.append(LegalAction(
                        action=BetAction.RAISE,
                        min_amount=min_raise_total,
                        max_amount=acting_rp.committed_this_street + stack,
                    ))

                if stack > 0:
                    legal_actions.append(LegalAction(
                        action=BetAction.ALL_IN, min_amount=stack, max_amount=stack,
                    ))

        is_showdown_ready = (
            game_round.street == Street.SHOWDOWN
            or game_round.status == RoundStatus.COMPLETED
        )

        return TableStateResponse(
            round_id=round_id,
            game_id=game_round.game_id,
            round_number=game_round.round_number,
            street=game_round.street,
            pot_amount=game_round.pot_amount,
            acting_player_id=game_round.acting_player_id,
            current_highest_bet=game_round.current_highest_bet,
            minimum_raise_amount=game_round.minimum_raise_amount,
            is_action_closed=game_round.is_action_closed,
            state_version=game_round.state_version,
            dealer_seat=game_round.dealer_seat,
            small_blind_seat=game_round.small_blind_seat,
            big_blind_seat=game_round.big_blind_seat,
            last_aggressor_seat=game_round.last_aggressor_seat,
            call_amount=computed_call_amount,
            is_showdown_ready=is_showdown_ready,
            legal_actions=legal_actions,
            players=[round_player_to_response(rp) for rp in round_players],
        )