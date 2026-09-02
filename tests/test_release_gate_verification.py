from typing import Any

import pytest

from ci import verify_release_gate

COMMIT_SHA = "c" * 40
TAG_OBJECT_SHA = "t" * 40


def mock_api(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, Any],
) -> None:
    def api(repository: str, path: str, token: str) -> Any:
        assert repository == "owner/repo"
        assert token == "token"
        return responses[path]

    monkeypatch.setattr(verify_release_gate, "_api", api)


def annotated_tag(
    tag: str,
    *,
    verified: bool,
    reason: str,
    target_type: str = "commit",
) -> dict[str, Any]:
    return {
        "tag": tag,
        "object": {"type": target_type, "sha": COMMIT_SHA},
        "verification": {
            "verified": verified,
            "reason": reason,
            "verified_at": "2026-09-01T12:00:00Z" if verified else None,
            "signature": "not copied to evidence",
            "payload": "not copied to evidence",
        },
    }


@pytest.mark.parametrize("tag", ["v0.1.0a1", "v0.1.0b1", "v0.1.0rc1"])
def test_prerelease_accepts_lightweight_tag(
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
) -> None:
    mock_api(
        monkeypatch,
        {f"git/ref/tags/{tag}": {"object": {"type": "commit", "sha": COMMIT_SHA}}},
    )

    commit, evidence = verify_release_gate._tag_commit("owner/repo", tag, "token")

    assert commit == COMMIT_SHA
    assert evidence == {
        "kind": "lightweight",
        "signature_required": False,
        "verified": False,
        "reason": "unsigned",
        "verified_at": None,
    }


def test_prerelease_accepts_unsigned_annotated_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v0.1.0rc1"
    mock_api(
        monkeypatch,
        {
            f"git/ref/tags/{tag}": {"object": {"type": "tag", "sha": TAG_OBJECT_SHA}},
            f"git/tags/{TAG_OBJECT_SHA}": annotated_tag(
                tag,
                verified=False,
                reason="unsigned",
            ),
        },
    )

    commit, evidence = verify_release_gate._tag_commit("owner/repo", tag, "token")

    assert commit == COMMIT_SHA
    assert evidence["kind"] == "annotated"
    assert evidence["signature_required"] is False
    assert evidence["verified"] is False


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.1.0.post1"])
def test_stable_release_accepts_verified_annotated_tag(
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
) -> None:
    mock_api(
        monkeypatch,
        {
            f"git/ref/tags/{tag}": {"object": {"type": "tag", "sha": TAG_OBJECT_SHA}},
            f"git/tags/{TAG_OBJECT_SHA}": annotated_tag(
                tag,
                verified=True,
                reason="valid",
            ),
        },
    )

    commit, evidence = verify_release_gate._tag_commit("owner/repo", tag, "token")

    assert commit == COMMIT_SHA
    assert evidence == {
        "kind": "annotated",
        "sha": TAG_OBJECT_SHA,
        "signature_required": True,
        "verified": True,
        "reason": "valid",
        "verified_at": "2026-09-01T12:00:00Z",
    }
    assert "signature" not in evidence
    assert "payload" not in evidence


def test_verified_tag_result_is_included_in_release_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v0.1.0"
    workflow = "ci.yml"
    mock_api(
        monkeypatch,
        {
            f"git/ref/tags/{tag}": {"object": {"type": "tag", "sha": TAG_OBJECT_SHA}},
            f"git/tags/{TAG_OBJECT_SHA}": annotated_tag(
                tag,
                verified=True,
                reason="valid",
            ),
            f"compare/{COMMIT_SHA}...main": {"merge_base_commit": {"sha": COMMIT_SHA}},
            (
                f"actions/workflows/{workflow}/runs?head_sha={COMMIT_SHA}"
                "&status=completed&per_page=100"
            ): {
                "workflow_runs": [
                    {
                        "id": 42,
                        "event": "push",
                        "conclusion": "success",
                        "head_sha": COMMIT_SHA,
                    }
                ]
            },
        },
    )

    evidence = verify_release_gate.verify(
        "owner/repo",
        COMMIT_SHA,
        tag,
        "token",
        [workflow],
        attempts=1,
        interval=0,
    )

    assert evidence["tag_object"] == {
        "kind": "annotated",
        "sha": TAG_OBJECT_SHA,
        "signature_required": True,
        "verified": True,
        "reason": "valid",
        "verified_at": "2026-09-01T12:00:00Z",
    }


def test_stable_release_rejects_lightweight_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v0.1.0"
    mock_api(
        monkeypatch,
        {f"git/ref/tags/{tag}": {"object": {"type": "commit", "sha": COMMIT_SHA}}},
    )

    with pytest.raises(RuntimeError, match="signed annotated tag"):
        verify_release_gate._tag_commit("owner/repo", tag, "token")


@pytest.mark.parametrize("reason", ["unsigned", "unknown_key", "expired_key"])
def test_stable_release_rejects_unverified_annotated_tag(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    tag = "v0.1.0"
    mock_api(
        monkeypatch,
        {
            f"git/ref/tags/{tag}": {"object": {"type": "tag", "sha": TAG_OBJECT_SHA}},
            f"git/tags/{TAG_OBJECT_SHA}": annotated_tag(
                tag,
                verified=False,
                reason=reason,
            ),
        },
    )

    with pytest.raises(RuntimeError, match=reason):
        verify_release_gate._tag_commit("owner/repo", tag, "token")


def test_annotated_tag_name_must_match_release_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v0.1.0"
    mock_api(
        monkeypatch,
        {
            f"git/ref/tags/{tag}": {"object": {"type": "tag", "sha": TAG_OBJECT_SHA}},
            f"git/tags/{TAG_OBJECT_SHA}": annotated_tag(
                "v0.1.1",
                verified=True,
                reason="valid",
            ),
        },
    )

    with pytest.raises(RuntimeError, match="name does not match"):
        verify_release_gate._tag_commit("owner/repo", tag, "token")


@pytest.mark.parametrize("tag", ["0.1.0", "vnot-a-version", "v0.1.0.dev1"])
def test_nonrelease_tag_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tag: str,
) -> None:
    def unexpected_api(repository: str, path: str, token: str) -> Any:
        raise AssertionError("invalid release tag must be rejected before API access")

    monkeypatch.setattr(verify_release_gate, "_api", unexpected_api)

    with pytest.raises(RuntimeError):
        verify_release_gate._tag_commit("owner/repo", tag, "token")
