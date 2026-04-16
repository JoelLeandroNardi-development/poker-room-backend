from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.helpers import MockMessage, SAMPLE_DT

@pytest.fixture
def sample_datetime():
    return SAMPLE_DT

@pytest.fixture
def rabbit_channel_mock():
    mock = AsyncMock()
    mock.set_qos = AsyncMock()
    mock.declare_exchange = AsyncMock()
    mock.declare_queue = AsyncMock()
    mock.get_queue = AsyncMock()
    return mock

@pytest.fixture
def rabbit_message_mock():
    mock = AsyncMock()
    mock.body = json.dumps({"test": "payload"}).encode("utf-8")
    mock.headers = {}
    mock.content_type = "application/json"
    mock.ack = AsyncMock()
    mock.reject = AsyncMock()
    mock.nack = AsyncMock()
    return mock

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    return session
