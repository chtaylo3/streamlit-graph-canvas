"""Exercise startup failures without launching Streamlit or a TLS proxy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def proxy(monkeypatch):
    path = Path(__file__).parent / "e2e/run_csp_proxy.py"
    spec = importlib.util.spec_from_file_location("csp_proxy_startup_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("SGC_CSP_CERTIFICATE", "test-cert.pem")
    monkeypatch.setenv("SGC_CSP_PRIVATE_KEY", "test-key.pem")
    child = MagicMock()
    child.poll.return_value = None
    monkeypatch.setattr(module.subprocess, "Popen", MagicMock(return_value=child))
    monkeypatch.setattr(module.time, "sleep", MagicMock())
    monkeypatch.setattr(module.uvicorn, "run", MagicMock())
    return module, child


def test_health_read_timeout_retries_then_starts_proxy(proxy, monkeypatch):
    module, child = proxy
    response = MagicMock()
    response.__enter__.return_value.status = 200
    request = MagicMock(side_effect=[TimeoutError("read timed out"), response])
    monkeypatch.setattr(module.urllib.request, "urlopen", request)

    module.main()

    assert request.call_count == 2
    module.time.sleep.assert_called_once_with(0.25)
    module.uvicorn.run.assert_called_once()
    child.terminate.assert_called_once()
    child.wait.assert_called_once_with(timeout=15)


def test_repeated_health_timeouts_fail_within_existing_retry_limit(proxy, monkeypatch):
    module, child = proxy
    request = MagicMock(side_effect=TimeoutError("read timed out"))
    monkeypatch.setattr(module.urllib.request, "urlopen", request)

    with pytest.raises(RuntimeError, match="Streamlit health check timed out"):
        module.main()

    assert request.call_count == 120
    assert module.time.sleep.call_count == 119
    module.uvicorn.run.assert_not_called()
    child.terminate.assert_called_once()
    child.wait.assert_called_once_with(timeout=15)
