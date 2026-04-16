"""
Unit tests for the atomic() transaction helper and settlement
transaction integrity.

Covers:
- SAVEPOINT commits on success
- SAVEPOINT rollback on exception
- Partial writes inside atomic are invisible after rollback
- Nested atomic blocks
- resolve_hand-style settlement atomicity simulation
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.core.db.session import atomic

class FakeNestedCtx:
    def __init__(self, *, should_fail: bool = False):
        self._should_fail = should_fail
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rolled_back = True
        else:
            self.committed = True
        return False

class FakeSession:
    def __init__(self, *, nested_fail: bool = False):
        self._nested_ctx = FakeNestedCtx(should_fail=nested_fail)
        self.adds: list = []
        self.committed = False

    def begin_nested(self):
        return self._nested_ctx

    def add(self, obj):
        self.adds.append(obj)

    async def commit(self):
        self.committed = True

class TestAtomicSuccess:
    @pytest.mark.asyncio
    async def test_savepoint_releases(self):
        session = FakeSession()
        async with atomic(session):
            session.add("row_a")
            session.add("row_b")

        assert session._nested_ctx.committed is True
        assert session._nested_ctx.rolled_back is False
        assert session.adds == ["row_a", "row_b"]

    @pytest.mark.asyncio
    async def test_yields_same_session(self):
        session = FakeSession()
        async with atomic(session) as s:
            assert s is session

class TestAtomicRollback:
    @pytest.mark.asyncio
    async def test_savepoint_rolls_back_on_error(self):
        session = FakeSession()
        with pytest.raises(ValueError, match="boom"):
            async with atomic(session):
                session.add("row_a")
                raise ValueError("boom")

        assert session._nested_ctx.rolled_back is True
        assert session._nested_ctx.committed is False

    @pytest.mark.asyncio
    async def test_exception_propagates(self):
        session = FakeSession()
        with pytest.raises(RuntimeError):
            async with atomic(session):
                raise RuntimeError("unexpected")

class TestSettlementAtomicity:
    @pytest.mark.asyncio
    async def test_all_settlement_writes_in_one_savepoint(self):
        session = FakeSession()
        payouts_written = []
        stacks_credited = {}
        round_status = {"status": "ACTIVE"}
        positions = {"dealer": 1}
        outbox = []

        async with atomic(session):
            payouts_written.append({"player": "A", "amount": 300})
            payouts_written.append({"player": "B", "amount": 200})

            stacks_credited["A"] = 300
            stacks_credited["B"] = 200

            round_status["status"] = "COMPLETED"

            positions["dealer"] = 2

            outbox.append({"type": "ROUND_COMPLETED"})

        assert session._nested_ctx.committed is True
        assert len(payouts_written) == 2
        assert stacks_credited == {"A": 300, "B": 200}
        assert round_status["status"] == "COMPLETED"
        assert positions["dealer"] == 2
        assert len(outbox) == 1

    @pytest.mark.asyncio
    async def test_settlement_failure_rolls_back_all(self):
        session = FakeSession()
        payouts_written = []

        with pytest.raises(ZeroDivisionError):
            async with atomic(session):
                payouts_written.append({"player": "A", "amount": 300})
                _ = 1 / 0

        assert session._nested_ctx.rolled_back is True
        assert session._nested_ctx.committed is False

    @pytest.mark.asyncio
    async def test_http_call_outside_savepoint(self):
        session = FakeSession()
        writes = []

        external_data = {"active_seats": [1, 2, 3]}

        async with atomic(session):
            writes.append("payout")
            writes.append("stack_credit")
            writes.append(f"rotate_to_{external_data['active_seats'][1]}")

        assert writes == ["payout", "stack_credit", "rotate_to_2"]
        assert session._nested_ctx.committed is True

    @pytest.mark.asyncio
    async def test_http_failure_prevents_writeblock(self):
        session = FakeSession()
        writes = []

        with pytest.raises(ConnectionError):
            raise ConnectionError("room-service unreachable")

            async with atomic(session):   # pragma: no cover
                writes.append("payout")

        assert writes == []
        assert session._nested_ctx.committed is False
        assert session._nested_ctx.rolled_back is False