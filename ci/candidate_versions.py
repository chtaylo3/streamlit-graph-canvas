"""Select stable candidate releases old enough for advisory testing."""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from packaging.version import InvalidVersion, Version


def select_release(
    releases: dict[str, str],
    *,
    now: dt.datetime,
    minimum: str,
    days: int = 7,
    baseline: str | None = None,
) -> str:
    eligible = []
    floor = max(Version(minimum), Version(baseline or minimum))
    for raw, timestamp in releases.items():
        try:
            version = Version(raw)
            released = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if (
                not version.is_prerelease
                and not version.is_devrelease
                and version >= floor
                and released <= now - dt.timedelta(days=days)
            ):
                eligible.append((version, raw))
        except (InvalidVersion, ValueError, TypeError):
            continue
    if not eligible:
        # An explicitly approved baseline can be newer than the cooldown. Never
        # use this exception for an unknown, yanked, prerelease, or future release.
        if baseline in releases:
            version = Version(baseline)
            released = dt.datetime.fromisoformat(
                releases[baseline].replace("Z", "+00:00")
            )
            if (
                not version.is_prerelease
                and not version.is_devrelease
                and version >= floor
                and released <= now
            ):
                return baseline
        raise ValueError(f"no stable release at least {days} days old")
    return max(eligible)[1]


def candidate_version(
    ecosystem: str,
    name: str,
    minimum: str,
    *,
    baseline: str | None = None,
    selections: list[dict[str, Any]] | None = None,
) -> str:
    if not re.fullmatch(r"[@a-zA-Z0-9_./-]+", name):
        raise ValueError("invalid package name")
    encoded = urllib.parse.quote(name, safe="")
    url = (
        f"https://pypi.org/pypi/{encoded}/json"
        if ecosystem == "python"
        else f"https://registry.npmjs.org/{encoded}"
    )
    evidence: dict[str, Any] = {
        "ecosystem": ecosystem,
        "package": name,
        "minimum": minimum,
        "baseline": baseline,
        "cooldown_days": 7,
        "status": "failed",
    }
    if selections is not None:
        selections.append(evidence)
    try:
        return _resolve(url, ecosystem, minimum, baseline, evidence)
    except Exception as error:
        evidence["error"] = str(error)
        raise ValueError(
            f"candidate selection failed for {ecosystem} {name}: {error}"
        ) from error


def _resolve(
    url: str,
    ecosystem: str,
    minimum: str,
    baseline: str | None,
    evidence: dict[str, Any],
) -> str:
    with urllib.request.urlopen(url, timeout=30) as response:
        data: dict[str, Any] = json.load(response)
    if ecosystem == "python":
        releases = {}
        for version, files in data["releases"].items():
            timestamps = [
                f["upload_time_iso_8601"] for f in files if not f.get("yanked")
            ]
            if timestamps:
                releases[version] = min(timestamps)
    else:
        releases = {
            version: timestamp
            for version, timestamp in data["time"].items()
            if version in data["versions"]
            and not data["versions"][version].get("deprecated")
        }
    now = dt.datetime.now(dt.UTC)
    if baseline in releases:
        released = dt.datetime.fromisoformat(releases[baseline].replace("Z", "+00:00"))
        evidence.update(
            baseline_released_at=released.isoformat(),
            baseline_eligible_at=(released + dt.timedelta(days=7)).isoformat(),
        )
    selected = select_release(releases, now=now, minimum=minimum, baseline=baseline)
    released = dt.datetime.fromisoformat(releases[selected].replace("Z", "+00:00"))
    retained = released > now - dt.timedelta(days=7)
    evidence.update(
        status="selected",
        selected=selected,
        released_at=released.isoformat(),
        eligible_at=(released + dt.timedelta(days=7)).isoformat(),
        reason="approved_baseline_retained" if retained else "aged_candidate",
    )
    return selected
