"""The live stream constructor call. This is a regression guard, not a
behavioral test - the failure mode (a silently dead socket) only manifests
over hours on a real connection and cannot be reproduced quickly offline.
"""
from unittest.mock import MagicMock, patch

from agent import ingest


def test_run_sets_a_data_timeout_so_a_dead_socket_gets_noticed():
    # Live: without this, a "connected but mute" socket produced zero bars
    # for ~19 hours across an entire trading session with no error raised,
    # because alpaca-py's ping/pong keepalive does not catch this failure
    # mode and data_timeout defaults to None (disabled).
    with patch("agent.ingest.StockDataStream") as mock_stream_cls:
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        ingest.run(conn=MagicMock())

        _, kwargs = mock_stream_cls.call_args
        assert kwargs.get("data_timeout") is not None
        assert kwargs["data_timeout"] > 0
