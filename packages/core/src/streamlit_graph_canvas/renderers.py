"""Static renderer discovery, validation, and explicit enablement."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import NoReturn, Protocol
from urllib.parse import unquote, urlparse

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .errors import Diagnostic, ValidationError
from .primitives import BadgeContext, Prim

RENDERER_API = 1
ENTRY_POINT_GROUP = "streamlit_graph_canvas.renderers"
_KIND_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$"
)
_PYTHON_REFERENCE_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
    r":[A-Za-z_][A-Za-z0-9_]*$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class BadgeRenderer(Protocol):
    kind: str
    renderer_api: int

    def render(
        self, data: object, options: Mapping[str, object], context: BadgeContext
    ) -> Sequence[Prim]: ...


@dataclass(frozen=True, slots=True)
class RendererKind:
    kind: str
    python: str | None
    javascript: str | None
    transports: frozenset[str]


@dataclass(frozen=True, slots=True)
class RendererManifest:
    distribution: str
    version: str
    manifest_schema: int
    renderer_api: str
    kinds: tuple[RendererKind, ...]
    assets: Mapping[str, str]
    path: Path


@dataclass(frozen=True, slots=True)
class EnabledRenderer:
    declaration: RendererKind
    implementation: BadgeRenderer | None
    distribution: str
    version: str


@dataclass(frozen=True, slots=True)
class RendererRegistry:
    renderers: Mapping[str, EnabledRenderer]

    def require(self, kind: str, transport: str) -> EnabledRenderer:
        renderer = self.renderers.get(kind)
        if renderer is None:
            _fail(
                "SGC_RENDERER_NOT_ENABLED",
                f"Renderer kind {kind!r} is not enabled.",
                "Explicitly enable its installed renderer distribution.",
                kind,
            )
        if transport not in renderer.declaration.transports:
            _fail(
                "SGC_RENDERER_TRANSPORT",
                f"Renderer does not support transport {transport!r}.",
                "Choose a transport declared by the renderer manifest.",
                kind,
            )
        return renderer


def _fail(code: str, message: str, action: str, subject: str | None = None) -> NoReturn:
    raise ValidationError(Diagnostic(code, message, action, subject))


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _manifest_path(dist: importlib.metadata.Distribution) -> Path:
    matches = [
        Path(str(dist.locate_file(file)))
        for file in dist.files or ()
        if PurePosixPath(str(file)).name == "renderer.toml"
    ]
    # PEP 660 editable installs only record their .pth file. Resolve their local
    # source tree from standardized metadata without importing plugin code.
    if not matches and (direct_url := dist.read_text("direct_url.json")):
        try:
            metadata = json.loads(direct_url)
            parsed = urlparse(metadata["url"])
            editable = metadata.get("dir_info", {}).get("editable") is True
            root = Path(unquote(parsed.path))
            if parsed.scheme == "file" and editable and root.is_dir():
                matches = list(root.glob("src/*/renderer.toml"))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            matches = []
    if len(matches) != 1:
        message = (
            "Renderer distribution must contain exactly one renderer.toml; "
            f"found {len(matches)}."
        )
        _fail(
            "SGC_MANIFEST_COUNT",
            message,
            "Package one static renderer.toml inside the import package.",
            dist.metadata["Name"],
        )
    return matches[0]


def _safe_asset_path(value: str, subject: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        _fail(
            "SGC_MANIFEST_ASSET_PATH",
            f"Unsafe renderer asset path {value!r}.",
            "Use a package-relative path without traversal segments.",
            subject,
        )
    return path


def parse_renderer_manifest(
    dist: importlib.metadata.Distribution,
) -> RendererManifest:
    """Read and validate a static renderer manifest without importing its code."""

    path = _manifest_path(dist)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        _fail(
            "SGC_MANIFEST_PARSE",
            f"Renderer manifest cannot be parsed: {error}.",
            "Correct the TOML syntax and rebuild the wheel.",
            dist.metadata["Name"],
        )
    allowed = {
        "manifest_schema",
        "distribution",
        "version",
        "renderer_api",
        "renderers",
        "assets",
    }
    required = {
        "manifest_schema",
        "distribution",
        "version",
        "renderer_api",
        "renderers",
    }
    missing = sorted(required - raw.keys())
    if missing:
        _fail(
            "SGC_MANIFEST_REQUIRED",
            f"Renderer manifest is missing fields: {missing}.",
            "Add every required manifest field.",
            dist.metadata["Name"],
        )
    unknown = sorted(raw.keys() - allowed)
    if unknown:
        _fail(
            "SGC_MANIFEST_UNKNOWN",
            f"Renderer manifest contains unknown fields: {unknown}.",
            "Remove unknown fields or use a supported manifest schema.",
            dist.metadata["Name"],
        )
    if not all(
        isinstance(raw[name], str)
        for name in ("distribution", "version", "renderer_api")
    ):
        _fail(
            "SGC_MANIFEST_TYPE",
            "Distribution, version, and renderer_api must be strings.",
            "Use quoted TOML strings for manifest identity and compatibility.",
            dist.metadata["Name"],
        )
    distribution = raw["distribution"]
    version = raw["version"]
    if _normalize(distribution) != _normalize(dist.metadata["Name"]):
        _fail(
            "SGC_MANIFEST_DISTRIBUTION",
            "Manifest distribution does not match installed metadata.",
            "Set distribution to the installed project name.",
            distribution,
        )
    try:
        versions_match = Version(version) == Version(dist.version)
    except InvalidVersion as error:
        _fail(
            "SGC_MANIFEST_VERSION",
            f"Renderer version is not valid: {error}.",
            "Use a valid PEP 440 package version.",
            distribution,
        )
    if not versions_match:
        message = (
            f"Manifest version {version!r} does not match installed version "
            f"{dist.version!r}."
        )
        _fail(
            "SGC_MANIFEST_VERSION",
            message,
            "Build the manifest and wheel with the same version.",
            distribution,
        )
    if not isinstance(raw["manifest_schema"], int) or raw["manifest_schema"] != 1:
        _fail(
            "SGC_MANIFEST_SCHEMA",
            f"Unsupported manifest schema {raw['manifest_schema']!r}.",
            "Use manifest schema version 1.",
            distribution,
        )
    try:
        compatible = Version(str(RENDERER_API)) in SpecifierSet(
            str(raw["renderer_api"])
        )
    except Exception as error:
        _fail(
            "SGC_RENDERER_API_RANGE",
            f"Invalid renderer API range: {error}.",
            "Use a PEP 440 range such as '>=1,<2'.",
            distribution,
        )
    if not compatible:
        _fail(
            "SGC_RENDERER_API_INCOMPATIBLE",
            f"Renderer API range {raw['renderer_api']!r} excludes API {RENDERER_API}.",
            "Install compatible core and renderer versions.",
            distribution,
        )
    renderer_items = raw["renderers"]
    if not isinstance(renderer_items, list) or not renderer_items:
        _fail(
            "SGC_MANIFEST_RENDERERS",
            "renderers must be a non-empty array of tables.",
            "Declare at least one [[renderers]] table.",
            distribution,
        )
    declarations: list[RendererKind] = []
    seen: set[str] = set()
    for item in renderer_items:
        if not isinstance(item, dict):
            _fail(
                "SGC_MANIFEST_RENDERER_TYPE",
                "Every renderer declaration must be a TOML table.",
                "Use one [[renderers]] table per renderer kind.",
                distribution,
            )
        item_unknown = sorted(
            item.keys() - {"kind", "python", "javascript", "transports"}
        )
        if item_unknown:
            _fail(
                "SGC_MANIFEST_RENDERER_UNKNOWN",
                f"Renderer declaration contains unknown fields: {item_unknown}.",
                "Remove unknown renderer fields.",
                distribution,
            )
        kind = item.get("kind", "")
        if not isinstance(kind, str):
            kind = ""
        if not _KIND_PATTERN.fullmatch(kind):
            _fail(
                "SGC_RENDERER_KIND",
                f"Renderer kind {kind!r} is not globally namespaced.",
                "Use the form 'vendor/package/kind'.",
                distribution,
            )
        if kind in seen:
            _fail(
                "SGC_RENDERER_DUPLICATE_KIND",
                f"Renderer kind {kind!r} is declared more than once.",
                "Keep one declaration for each canonical kind.",
                distribution,
            )
        seen.add(kind)
        transport_items = item.get("transports")
        if not isinstance(transport_items, list) or not all(
            isinstance(value, str) for value in transport_items
        ):
            _fail(
                "SGC_RENDERER_TRANSPORT",
                f"Renderer transports for {kind!r} must be an array of strings.",
                "Declare one or more supported transport names.",
                distribution,
            )
        transports = frozenset(transport_items)
        if not transports or not transports <= {"prims", "javascript", "atlas"}:
            _fail(
                "SGC_RENDERER_TRANSPORT",
                f"Invalid transports for {kind!r}: {sorted(transports)}.",
                "Declare one or more of prims, javascript, or atlas.",
                distribution,
            )
        python = item.get("python")
        javascript = item.get("javascript")
        if python is not None and (
            not isinstance(python, str)
            or not _PYTHON_REFERENCE_PATTERN.fullmatch(python)
        ):
            _fail(
                "SGC_RENDERER_REFERENCE",
                f"Invalid Python renderer reference {python!r}.",
                "Use 'package.module:attribute'.",
                kind,
            )
        if javascript is not None and not isinstance(javascript, str):
            _fail(
                "SGC_RENDERER_REFERENCE",
                "JavaScript renderer references must be package-relative strings.",
                "Use a reviewed asset path from the manifest.",
                kind,
            )
        if "prims" in transports and python is None:
            _fail(
                "SGC_RENDERER_IMPLEMENTATION",
                "PRIMS renderers require a Python implementation.",
                "Declare a package module and attribute in the python field.",
                kind,
            )
        if "javascript" in transports and javascript is None:
            _fail(
                "SGC_RENDERER_IMPLEMENTATION",
                "JavaScript renderers require a packaged implementation asset.",
                "Declare its package-relative path in the javascript field.",
                kind,
            )
        declarations.append(RendererKind(kind, python, javascript, transports))
    assets = raw.get("assets", {})
    if not isinstance(assets, dict):
        _fail(
            "SGC_MANIFEST_ASSETS",
            "assets must be a path-to-SHA256 table.",
            "Declare assets as TOML table entries.",
            distribution,
        )
    verified_assets: dict[str, str] = {}
    package_root = path.parent
    for value, expected_hash in assets.items():
        if not isinstance(value, str) or not isinstance(expected_hash, str):
            _fail(
                "SGC_MANIFEST_ASSETS",
                "Asset paths and SHA256 values must be strings.",
                "Declare assets as quoted path-to-hash entries.",
                distribution,
            )
        if not _SHA256_PATTERN.fullmatch(expected_hash):
            _fail(
                "SGC_MANIFEST_ASSET_HASH",
                f"Asset hash for {value!r} is not a lowercase SHA256 digest.",
                "Store the asset's full lowercase SHA256 digest.",
                distribution,
            )
        relative = _safe_asset_path(value, distribution)
        asset = package_root.joinpath(*relative.parts).resolve()
        if not asset.is_relative_to(package_root.resolve()) or not asset.is_file():
            _fail(
                "SGC_MANIFEST_ASSET_MISSING",
                f"Declared renderer asset {value!r} is missing.",
                "Package the asset under the manifest directory.",
                distribution,
            )
        actual_hash = hashlib.sha256(asset.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            _fail(
                "SGC_MANIFEST_ASSET_HASH",
                f"Asset hash mismatch for {value!r}.",
                "Regenerate the manifest from reviewed package assets.",
                distribution,
            )
        verified_assets[value] = actual_hash
    for declaration in declarations:
        if declaration.javascript is not None:
            javascript_path = str(
                _safe_asset_path(declaration.javascript, declaration.kind)
            )
            if javascript_path not in verified_assets:
                message = (
                    f"JavaScript implementation {javascript_path!r} is not a "
                    "hashed asset."
                )
                _fail(
                    "SGC_MANIFEST_ASSET_MISSING",
                    message,
                    "Declare the implementation and its SHA256 in assets.",
                    declaration.kind,
                )
    return RendererManifest(
        distribution,
        version,
        1,
        str(raw["renderer_api"]),
        tuple(declarations),
        MappingProxyType(verified_assets),
        path,
    )


def discover_renderer_manifests() -> tuple[RendererManifest, ...]:
    """Discover installed renderer metadata without loading entry-point values."""

    distributions: dict[str, importlib.metadata.Distribution] = {}
    for entry_point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        dist = entry_point.dist
        if dist is not None:
            distributions[_normalize(dist.metadata["Name"])] = dist
    return tuple(
        parse_renderer_manifest(distributions[name]) for name in sorted(distributions)
    )


def _load_implementation(reference: str, expected_kind: str) -> BadgeRenderer:
    if ":" not in reference:
        _fail(
            "SGC_RENDERER_REFERENCE",
            f"Invalid Python renderer reference {reference!r}.",
            "Use 'package.module:attribute'.",
            expected_kind,
        )
    module_name, attribute = reference.split(":", 1)
    implementation = getattr(importlib.import_module(module_name), attribute)
    renderer = implementation() if isinstance(implementation, type) else implementation
    if (
        getattr(renderer, "kind", None) != expected_kind
        or getattr(renderer, "renderer_api", None) != RENDERER_API
    ):
        _fail(
            "SGC_RENDERER_CONTRACT",
            "Loaded renderer kind or API does not match its static manifest.",
            "Make implementation metadata match the reviewed manifest.",
            expected_kind,
        )
    return renderer


def enable_renderers(distributions: Sequence[str]) -> RendererRegistry:
    """Validate and explicitly load only the named installed renderer packages."""

    requested = {_normalize(name) for name in distributions}
    available = {
        _normalize(manifest.distribution): manifest
        for manifest in discover_renderer_manifests()
    }
    missing = sorted(requested - available.keys())
    if missing:
        _fail(
            "SGC_RENDERER_DISTRIBUTION_MISSING",
            f"Renderer distributions are not installed: {missing}.",
            "Install the wheels before explicitly enabling them.",
        )
    selected: dict[str, tuple[RendererKind, RendererManifest]] = {}
    for name in sorted(requested):
        manifest = available[name]
        for declaration in manifest.kinds:
            if declaration.kind in selected:
                _fail(
                    "SGC_RENDERER_KIND_CONFLICT",
                    f"Enabled packages both provide {declaration.kind!r}.",
                    "Enable only one provider for a canonical renderer kind.",
                    declaration.kind,
                )
            selected[declaration.kind] = (declaration, manifest)
    enabled: dict[str, EnabledRenderer] = {}
    for kind in sorted(selected):
        declaration, manifest = selected[kind]
        implementation = (
            _load_implementation(declaration.python, declaration.kind)
            if declaration.python
            else None
        )
        enabled[declaration.kind] = EnabledRenderer(
            declaration, implementation, manifest.distribution, manifest.version
        )
    return RendererRegistry(MappingProxyType(enabled))
