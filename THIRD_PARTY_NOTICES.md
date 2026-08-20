# Third-party notices

AIShop Hermes Workbench is licensed under `AGPL-3.0-only`. Components listed
below remain subject to their own licenses. This inventory covers the direct
dependencies and source references declared by version 0.1.0-alpha; release
artifacts also include a machine-readable SBOM for transitive dependencies.

## Hermes Agent and Hermes Desktop interfaces

The AIShop plugin integration and local SDK type declarations reference the
public interfaces of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Direct development and runtime dependencies

| Ecosystem | Components | License |
| --- | --- | --- |
| Python | FastAPI, Pydantic, Ruff | MIT |
| Python | HTTPX, Starlette | BSD-3-Clause |
| Python | jsonschema, pytest | MIT |
| Python | Pillow | HPND / MIT-CMU style |
| npm | React, Vitest, esbuild | MIT |
| npm | TypeScript | Apache-2.0 |
| Android | AndroidX, Jetpack Compose | Apache-2.0 |
| Android | Kotlin, kotlinx.coroutines, kotlinx.serialization | Apache-2.0 |
| Android | OkHttp | Apache-2.0 |
| Android test | JUnit 4 | Eclipse Public License 1.0 |
| Build | Gradle Wrapper | Apache-2.0 |

Authoritative license texts and copyright notices are distributed by each
upstream package and are represented in the release SBOM. If this inventory
and an upstream artifact disagree, the upstream artifact's notice controls.
