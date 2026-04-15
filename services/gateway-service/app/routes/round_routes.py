from __future__ import annotations

from fastapi import APIRouter, Request

from ..clients.service_client import game_client
from ..utils.proxy import forward_response

router = APIRouter(prefix="/rounds", tags=["rounds"])

@router.get("/{round_id}")
async def get_round(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}")
    return forward_response(resp)

@router.post("/{round_id}/resolve")
async def resolve_hand(round_id: str, request: Request):
    body = await request.json()
    resp = await game_client.post(f"/rounds/{round_id}/resolve", json=body)
    return forward_response(resp)

@router.post("/{round_id}/advance-street")
async def advance_street(round_id: str):
    resp = await game_client.post(f"/rounds/{round_id}/advance-street")
    return forward_response(resp)

@router.post("/{round_id}/winner")
async def declare_winner(round_id: str, body: dict):
    resp = await game_client.post(f"/rounds/{round_id}/winner", json=body)
    return forward_response(resp)

@router.get("/{round_id}/ledger")
async def get_ledger(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/ledger")
    return forward_response(resp)

@router.get("/{round_id}/hand-state")
async def get_hand_state(round_id: str):
    resp = await game_client.get(f"/rounds/{round_id}/hand-state")
    return forward_response(resp)

@router.post("/{round_id}/corrections/reverse-action")
async def reverse_action(round_id: str, request: Request):
    body = await request.json()
    resp = await game_client.post(f"/rounds/{round_id}/corrections/reverse-action", json=body)
    return forward_response(resp)

@router.post("/{round_id}/corrections/adjust-stack")
async def adjust_stack(round_id: str, request: Request):
    body = await request.json()
    resp = await game_client.post(f"/rounds/{round_id}/corrections/adjust-stack", json=body)
    return forward_response(resp)

@router.post("/{round_id}/corrections/reopen-hand")
async def reopen_hand(round_id: str, request: Request):
    body = await request.json()
    resp = await game_client.post(f"/rounds/{round_id}/corrections/reopen-hand", json=body)
    return forward_response(resp)

@router.post("/{round_id}/corrections/correct-payout")
async def correct_payout(round_id: str, request: Request):
    body = await request.json()
    resp = await game_client.post(f"/rounds/{round_id}/corrections/correct-payout", json=body)
    return forward_response(resp)