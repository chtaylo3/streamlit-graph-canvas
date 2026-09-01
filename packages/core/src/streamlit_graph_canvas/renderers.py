"""Static renderer discovery, validation, and explicit enablement."""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import importlib.metadata
import json
import logging
import re
import threading
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import NoReturn, Protocol
from urllib.parse import unquote, urlparse

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .contract import RENDERER_API
from .errors import Diagnostic, ValidationError
from .primitives import BadgeContext, Prim

ENTRY_POINT_GROUP = "streamlit_graph_canvas.renderers"
LOGGER = logging.getLogger("streamlit_graph_canvas")
_KIND_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$"
)
_PYTHON_REFERENCE_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
    r":[A-Za-z_][A-Za-z0-9_]*$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_JAVASCRIPT_IDENTITY_PATTERN = re.compile(rb'const buildIdentity = "([0-9a-f]{64})";')
_ManifestCacheKey = tuple[str, str, str, str]
_AssetSignature = tuple[tuple[str, str], ...]
_MANIFEST_CACHE: dict[_ManifestCacheKey, tuple[RendererManifest, _AssetSignature]] = {}
_MANIFEST_CACHE_LOCK = threading.RLock()


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
    javascript_component: str | None = None
    javascript_entry: str | None = None
    javascript_identity: str | None = None


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
    javascript_hash: str | None = None


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
                candidates = [
                    *root.glob("*/renderer.toml"),
                    *root.glob("src/*/renderer.toml"),
                ]
                for entry_point in getattr(dist, "entry_points", ()):
                    if entry_point.group != ENTRY_POINT_GROUP:
                        continue
                    module = entry_point.value.partition(":")[0]
                    relative = Path(*module.split(".")).with_name("renderer.toml")
                    candidates.extend((root / relative, root / "src" / relative))
                matches = sorted(
                    {item.resolve() for item in candidates if item.is_file()}
                )
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


def _validate_javascript_component(
    package_root: Path,
    distribution: str,
    declaration: RendererKind,
) -> None:
    if (
        declaration.javascript is None
        or declaration.javascript_component is None
        or declaration.javascript_entry is None
    ):
        return
    component_manifest = package_root / "pyproject.toml"
    try:
        raw = tomllib.loads(component_manifest.read_text(encoding="utf-8"))
        project_name = raw["project"]["name"]
        components = raw["tool"]["streamlit"]["component"]["components"]
    except (KeyError, OSError, TypeError, tomllib.TOMLDecodeError) as error:
        _fail(
            "SGC_RENDERER_COMPONENT_MANIFEST",
            f"JavaScript renderer component manifest is invalid: {error}.",
            "Package a valid pyproject.toml beside renderer.toml.",
            declaration.kind,
        )
    if _normalize(project_name) != _normalize(distribution):
        _fail(
            "SGC_RENDERER_COMPONENT_OWNERSHIP",
            "JavaScript component project does not match its renderer distribution.",
            "Use a component declared by the explicitly enabled distribution.",
            declaration.kind,
        )
    matches = [
        item
        for item in components
        if f"{project_name}.{item.get('name')}" == declaration.javascript_component
    ]
    if len(matches) != 1:
        _fail(
            "SGC_RENDERER_COMPONENT_MANIFEST",
            "JavaScript component key is not declared exactly once.",
            "Declare the manifest component in the packaged pyproject.toml.",
            declaration.kind,
        )
    asset_root = package_root / _safe_asset_path(
        matches[0].get("asset_dir", ""), declaration.kind
    )
    component_asset = asset_root.joinpath(
        *_safe_asset_path(declaration.javascript_entry, declaration.kind).parts
    ).resolve()
    declared_asset = package_root.joinpath(
        *_safe_asset_path(declaration.javascript, declaration.kind).parts
    ).resolve()
    if component_asset != declared_asset or not component_asset.is_file():
        _fail(
            "SGC_RENDERER_COMPONENT_ASSET",
            "JavaScript component entry does not resolve to the hashed renderer asset.",
            "Align javascript, javascript_entry, and the component asset directory.",
            declaration.kind,
        )


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
            item.keys()
            - {
                "kind",
                "python",
                "javascript",
                "javascript_component",
                "javascript_entry",
                "javascript_identity",
                "transports",
            }
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
        javascript_component = item.get("javascript_component")
        javascript_entry = item.get("javascript_entry")
        javascript_identity = item.get("javascript_identity")
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
        if any(
            value is not None and (not isinstance(value, str) or not value)
            for value in (
                javascript_component,
                javascript_entry,
                javascript_identity,
            )
        ):
            _fail(
                "SGC_RENDERER_REFERENCE",
                "JavaScript component and entry references must be non-empty strings.",
                "Declare the installed component key and its asset-dir-relative entry.",
                kind,
            )
        if ({"prims", "atlas"} & transports) and python is None:
            _fail(
                "SGC_RENDERER_IMPLEMENTATION",
                "PRIMS and ATLAS renderers require a Python implementation.",
                "Declare a package module and attribute in the python field.",
                kind,
            )
        if "javascript" in transports and (
            javascript is None
            or javascript_component is None
            or javascript_entry is None
            or javascript_identity is None
        ):
            _fail(
                "SGC_RENDERER_IMPLEMENTATION",
                "JavaScript renderers require a packaged implementation asset.",
                "Declare javascript, javascript_component, javascript_entry, and "
                "javascript_identity.",
                kind,
            )
        if javascript_identity is not None and not _SHA256_PATTERN.fullmatch(
            javascript_identity
        ):
            _fail(
                "SGC_RENDERER_IDENTITY",
                "JavaScript renderer identity must be a lowercase SHA256 digest.",
                "Regenerate renderer assets and their immutable identity.",
                kind,
            )
        declarations.append(
            RendererKind(
                kind,
                python,
                javascript,
                transports,
                javascript_component,
                javascript_entry,
                javascript_identity,
            )
        )
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
            asset_hash = verified_assets[javascript_path]
            asset = package_root / javascript_path
            if not asset.name.endswith(f".{asset_hash}.js"):
                _fail(
                    "SGC_RENDERER_CONTENT_ADDRESS",
                    "JavaScript renderer filename does not contain its "
                    "final-byte SHA256.",
                    "Regenerate the content-addressed renderer asset.",
                    declaration.kind,
                )
            identities = _JAVASCRIPT_IDENTITY_PATTERN.findall(asset.read_bytes())
            expected_identity = declaration.javascript_identity
            if expected_identity is None or identities != [expected_identity.encode()]:
                _fail(
                    "SGC_RENDERER_IDENTITY",
                    "JavaScript renderer embedded identity differs from its manifest.",
                    "Regenerate the immutable renderer build identity.",
                    declaration.kind,
                )
            if declaration.javascript_entry is not None:
                _safe_asset_path(declaration.javascript_entry, declaration.kind)
            _validate_javascript_component(package_root, distribution, declaration)
    return RendererManifest(
        distribution,
        version,
        1,
        str(raw["renderer_api"]),
        tuple(declarations),
        MappingProxyType(verified_assets),
        path,
    )


def _cached_renderer_manifest(
    dist: importlib.metadata.Distribution,
) -> RendererManifest:
    with _MANIFEST_CACHE_LOCK:
        path = _manifest_path(dist)
        manifest_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = (
            _normalize(dist.metadata["Name"]),
            dist.version,
            str(path.resolve()),
            manifest_digest,
        )
        cached = _MANIFEST_CACHE.get(key)
        manifest: RendererManifest | None = None
        if cached is not None:
            manifest, expected_assets = cached
            try:
                current_assets = tuple(
                    (
                        asset,
                        hashlib.sha256(
                            (manifest.path.parent / asset).read_bytes()
                        ).hexdigest(),
                    )
                    for asset in sorted(manifest.assets)
                )
            except OSError:
                current_assets = ()
            if current_assets != expected_assets:
                del _MANIFEST_CACHE[key]
                manifest = None
        if manifest is None:
            for stale in tuple(_MANIFEST_CACHE):
                if stale[0] == key[0] and stale[2] == key[2]:
                    del _MANIFEST_CACHE[stale]
            try:
                manifest = parse_renderer_manifest(dist)
            except ValidationError as error:
                LOGGER.warning(
                    "Renderer manifest validation failed",
                    extra={
                        "sgc_event_code": error.diagnostic.code,
                        "sgc_renderer_distribution": dist.metadata["Name"],
                    },
                )
                raise
            asset_signature = tuple(sorted(manifest.assets.items()))
            _MANIFEST_CACHE[key] = (manifest, asset_signature)
        return manifest


def discover_renderer_manifests() -> tuple[RendererManifest, ...]:
    """Discover installed renderer metadata without loading entry-point values."""

    distributions = _renderer_distributions()
    return tuple(
        _cached_renderer_manifest(distributions[name]) for name in sorted(distributions)
    )


def _renderer_distributions() -> dict[str, importlib.metadata.Distribution]:
    distributions: dict[str, importlib.metadata.Distribution] = {}
    for entry_point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        dist = entry_point.dist
        if dist is not None:
            distributions[_normalize(dist.metadata["Name"])] = dist
    return distributions


def discover_renderer_diagnostics() -> tuple[Diagnostic, ...]:
    """Return non-fatal diagnostics for malformed installed renderer packages."""

    diagnostics: list[Diagnostic] = []
    for _, dist in sorted(_renderer_distributions().items()):
        try:
            _cached_renderer_manifest(dist)
        except ValidationError as error:
            diagnostics.append(error.diagnostic)
    return tuple(diagnostics)


def _editable_project_root(
    dist: importlib.metadata.Distribution,
) -> Path | None:
    try:
        direct = json.loads(dist.read_text("direct_url.json") or "{}")
        if not direct.get("dir_info", {}).get("editable"):
            return None
        parsed = urlparse(direct["url"])
        return Path(unquote(parsed.path)).resolve()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _distribution_module_origin(
    dist: importlib.metadata.Distribution, module_name: str
) -> Path | None:
    """Resolve a concrete leaf module from files owned by the selected distribution."""

    relative = Path(*module_name.split("."))
    suffixes = (".py", *importlib.machinery.EXTENSION_SUFFIXES)
    candidates = tuple(relative.with_suffix(suffix) for suffix in suffixes) + tuple(
        relative / f"__init__{suffix}" for suffix in suffixes
    )
    recorded: dict[Path, Path] = {}
    for item in dist.files or ():
        path = Path(str(item))
        try:
            located = Path(str(dist.locate_file(item))).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        recorded[path] = located
    for candidate in candidates:
        for recorded_path, located in recorded.items():
            if recorded_path == candidate and located.is_file():
                return located
    editable = _editable_project_root(dist)
    if editable is not None:
        for root in (editable / "src", editable):
            for candidate in candidates:
                origin = (root / candidate).resolve()
                if origin.is_relative_to(root.resolve()) and origin.is_file():
                    return origin
    return None


def _load_implementation(
    reference: str,
    expected_kind: str,
    dist: importlib.metadata.Distribution,
) -> BadgeRenderer:
    if ":" not in reference:
        _fail(
            "SGC_RENDERER_REFERENCE",
            f"Invalid Python renderer reference {reference!r}.",
            "Use 'package.module:attribute'.",
            expected_kind,
        )
    module_name, attribute = reference.split(":", 1)
    expected_origin = _distribution_module_origin(dist, module_name)
    if expected_origin is None:
        _fail(
            "SGC_RENDERER_MODULE_OWNERSHIP",
            f"Renderer implementation module {module_name!r} is not owned by "
            f"distribution {dist.metadata['Name']!r}.",
            "Reference a module packaged by the explicitly enabled distribution.",
            expected_kind,
        )
    module = importlib.import_module(module_name)
    actual_origin = getattr(getattr(module, "__spec__", None), "origin", None)
    if actual_origin is None or Path(actual_origin).resolve() != expected_origin:
        _fail(
            "SGC_RENDERER_MODULE_OWNERSHIP",
            f"Imported renderer module {module_name!r} did not resolve to its "
            "distribution-owned file.",
            "Remove namespace or import-path shadowing before enablement.",
            expected_kind,
        )
    implementation = getattr(module, attribute)
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
    available = _renderer_distributions()
    missing = sorted(requested - available.keys())
    if missing:
        _fail(
            "SGC_RENDERER_DISTRIBUTION_MISSING",
            f"Renderer distributions are not installed: {missing}.",
            "Install the wheels before explicitly enabling them.",
        )
    selected: dict[
        str,
        tuple[RendererKind, RendererManifest, importlib.metadata.Distribution],
    ] = {}
    for name in sorted(requested):
        dist = available[name]
        manifest = _cached_renderer_manifest(dist)
        for declaration in manifest.kinds:
            if declaration.kind in selected:
                _fail(
                    "SGC_RENDERER_KIND_CONFLICT",
                    f"Enabled packages both provide {declaration.kind!r}.",
                    "Enable only one provider for a canonical renderer kind.",
                    declaration.kind,
                )
            selected[declaration.kind] = (declaration, manifest, dist)
    enabled: dict[str, EnabledRenderer] = {}
    for kind in sorted(selected):
        declaration, manifest, dist = selected[kind]
        implementation = (
            _load_implementation(declaration.python, declaration.kind, dist)
            if declaration.python
            else None
        )
        enabled[declaration.kind] = EnabledRenderer(
            declaration,
            implementation,
            manifest.distribution,
            manifest.version,
            manifest.assets.get(declaration.javascript)
            if declaration.javascript is not None
            else None,
        )
    return RendererRegistry(MappingProxyType(enabled))
