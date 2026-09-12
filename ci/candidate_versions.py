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
    releases: dict[str, str], *, now: dt.datetime, minimum: str, days: int = 7
) -> str:
    eligible = []
    for raw, timestamp in releases.items():
        try:
            version = Version(raw)
            released = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if (
                not version.is_prerelease
                and not version.is_devrelease
                and version >= Version(minimum)
                and released <= now - dt.timedelta(days=days)
            ):
                eligible.append((version, raw))
        except (InvalidVersion, ValueError, TypeError):
            continue
    if not eligible:
        raise ValueError(f"no stable release at least {days} days old")
    return max(eligible)[1]


def candidate_version(ecosystem: str, name: str, minimum: str) -> str:
    if not re.fullmatch(r"[@a-zA-Z0-9_./-]+", name):
        raise ValueError("invalid package name")
    encoded = urllib.parse.quote(name, safe="")
    url = (
        f"https://pypi.org/pypi/{encoded}/json"
        if ecosystem == "python"
        else f"https://registry.npmjs.org/{encoded}"
    )
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
    return select_release(releases, now=dt.datetime.now(dt.UTC), minimum=minimum)
