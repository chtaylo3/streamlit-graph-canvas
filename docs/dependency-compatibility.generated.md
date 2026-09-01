# Generated dependency compatibility matrix

This file is generated from `ci/dependency-policy.toml` by
`ci/generate_dependency_docs.py`. Do not edit it manually.

## Toolchains

| Surface | Minimum/locked | Forward signal |
| --- | --- | --- |
| Python | 3.12 (3.12, 3.13, 3.14) | 3.15 |
| Node.js | >=24 <25 (locked 24) | 26 |

## Python runtime

| Dependency | Minimum | Supported | Forward | Risk |
| --- | --- | --- | --- | --- |
| streamlit | 1.62.0 | `>=1.62.0` | `streamlit>=1.62.0` | critical |
| packaging | 26.0 | `>=26.0` | `—` | high |
| Pillow | 12.3.0 | `>=12.3.0,<13` | `Pillow>=13.0.0a0` | critical |
| networkx | 3.6.1 | `>=3.6.1` | `networkx>=3.6.1` | medium |

## Browser and build dependencies

| Group | Dependency | Minimum | Supported | Forward | Coupled with | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| runtime | @streamlit/component-v2-lib | 0.2.0 | `^0.2.0` | `next` | streamlit | critical |
| runtime | @xyflow/react | 12.11.3 | `^12.11.3` | `next` | react,react-dom | critical |
| runtime | elkjs | 0.12.0 | `^0.12.0` | `next` | @xyflow/react | critical |
| runtime | react | 19.2.0 | `^19.2.0` | `canary` | react-dom,@xyflow/react | critical |
| runtime | react-dom | 19.2.0 | `^19.2.0` | `canary` | react,@xyflow/react | critical |
| build | @vitejs/plugin-react | 6.1.0 | `^6.1.0` | `—` | — | high |
| build | @types/react | 19.2.0 | `^19.2.0` | `—` | react,react-dom,@types/react-dom,@xyflow/react | high |
| build | @types/react-dom | 19.2.0 | `^19.2.0` | `—` | react,react-dom,@types/react,@xyflow/react | high |
| build | typescript | 7.0.2 | `^7.0.2` | `—` | — | high |
| build | vite | 8.2.0 | `^8.2.0` | `—` | — | high |
| build | vitest | 4.1.0 | `^4.1.0` | `—` | — | medium |
| test | @playwright/test | 1.52.0 | `^1.52.0` | `—` | — | high |
| test | @axe-core/playwright | 4.13.0 | `^4.13.0` | `—` | — | medium |
| test | @types/node | 24.0.0 | `^24.0.0` | `—` | — | low |
| test | typescript | 7.0.2 | `^7.0.2` | `—` | — | medium |

## CI signals

Blocking: locked, release-artifact, minimum, latest, security.

Advisory: forward, browser-beta.
