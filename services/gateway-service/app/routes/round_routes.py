from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..clients.service_client import game_client
from ..utils.proxy import forward_response
from shared.schemas.games import (
    RoundResponse, ResolveHandRequest, ResolveHandResponse,
    AdvanceStreetResponse, DeclareWinner, DeclareWinnerResponse,
    LedgerEntryResponse, HandStateResponse,
    ReverseActionRequest, AdjustStackRequest,
    ReopenHandRequest, CorrectPayoutRequest,
    ReplayResponse, TimelineResponse,
    SettlementExplanationResponse, ConsistencyCheckResponse,
    TableStateResponse,
)

router = APIRouter(prefix="/rounds", tags=["rounds"])

@router.get("/{round_id}", response_model=RoundResponse)
async def get_round(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}")
    return forward_response(resp)

@router.post("/{round_id}/resolve", response_model=ResolveHandResponse)
async def resolve_hand(round_id: str, data: ResolveHandRequest):
    resp = await game_client.post(f"/rounds/{round_id}/resolve", json=data.model_dump())
    return forward_response(resp)

@router.post("/{round_id}/advance-street", response_model=AdvanceStreetResponse)
async def advance_street(round_id: str):
    resp = await game_client.post(f"/rounds/{round_id}/advance-street")
    return forward_response(resp)

@router.post("/{round_id}/winner", response_model=DeclareWinnerResponse)
async def declare_winner(round_id: str, data: DeclareWinner):
    resp = await game_client.post(f"/rounds/{round_id}/winner", json=data.model_dump())
    return forward_response(resp)

@router.get("/{round_id}/ledger", response_model=list[LedgerEntryResponse])
async def get_ledger(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/ledger")
    return forward_response(resp)

@router.get("/{round_id}/hand-state", response_model=HandStateResponse)
async def get_hand_state(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/hand-state")
    return forward_response(resp)

@router.get("/{round_id}/replay", response_model=ReplayResponse)
async def get_replay(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/replay")
    return forward_response(resp)

@router.get("/{round_id}/timeline", response_model=TimelineResponse)
async def get_timeline(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/timeline")
    return forward_response(resp)

@router.get("/{round_id}/settlement-explanation", response_model=SettlementExplanationResponse)
async def get_settlement_explanation(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/settlement-explanation")
    return forward_response(resp)

@router.get("/{round_id}/consistency-check", response_model=ConsistencyCheckResponse)
async def check_consistency(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/consistency-check")
    return forward_response(resp)

@router.get("/{round_id}/table-state", response_model=TableStateResponse)
async def get_table_state(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/table-state")
    return forward_response(resp)

@router.websocket("/{round_id}/table-state/ws")
async def table_state_websocket(websocket: WebSocket, round_id: str):
    await websocket.accept()
    interval_seconds = 1.0
    try:
        raw_interval = websocket.query_params.get("interval")
        if raw_interval is not None:
            interval_seconds = max(0.25, min(float(raw_interval), 10.0))
    except ValueError:
        interval_seconds = 1.0

    try:
        while True:
            resp = await game_client.get(f"/rounds/{round_id}/table-state")
            if resp.status_code >= 400:
                await websocket.send_json({
                    "type": "error",
                    "status_code": resp.status_code,
                    "detail": resp.text,
                })
                await asyncio.sleep(interval_seconds)
                continue

            await websocket.send_json({
                "type": "table_state",
                "round_id": round_id,
                "data": resp.json(),
            })
            await asyncio.sleep(interval_seconds)
    except WebSocketDisconnect:
        return

@router.post("/{round_id}/corrections/reverse-action", response_model=LedgerEntryResponse)
async def reverse_action(round_id: str, data: ReverseActionRequest):
    resp = await game_client.post(f"/rounds/{round_id}/corrections/reverse-action", json=data.model_dump(exclude_none=True))
    return forward_response(resp)

@router.post("/{round_id}/corrections/adjust-stack", response_model=LedgerEntryResponse)
async def adjust_stack(round_id: str, data: AdjustStackRequest):
    resp = await game_client.post(f"/rounds/{round_id}/corrections/adjust-stack", json=data.model_dump(exclude_none=True))
    return forward_response(resp)

@router.post("/{round_id}/corrections/reopen-hand", response_model=LedgerEntryResponse)
async def reopen_hand(round_id: str, data: ReopenHandRequest):
    resp = await game_client.post(f"/rounds/{round_id}/corrections/reopen-hand", json=data.model_dump(exclude_none=True))
    return forward_response(resp)

@router.post("/{round_id}/corrections/correct-payout", response_model=LedgerEntryResponse)
async def correct_payout(round_id: str, data: CorrectPayoutRequest):
    resp = await game_client.post(f"/rounds/{round_id}/corrections/correct-payout", json=data.model_dump(exclude_none=True))
    return forward_response(resp)