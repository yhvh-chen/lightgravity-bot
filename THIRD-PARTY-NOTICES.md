# Third-party notices

LightGravity Bot is a local application built on Python and JavaScript
dependencies. This notice describes what the prebuilt release archive contains
and how dependency licenses are handled.

## Project license status

The repository does not currently contain a project `LICENSE` file, and no
public redistribution license has been selected by the project owner. This
notice does not grant a license for LightGravity Bot itself.

## Python runtime dependencies

Python dependencies are **not bundled** in the release archive. The archive
contains the project's `pyproject.toml`, `uv.lock`, and `.python-version`;
`uv sync --frozen --no-dev` downloads the locked packages from the configured
package index on the target machine.

The fixed production set is recorded in `uv.lock`. Direct runtime dependencies
declared by the project are:

| Package | Declared range | License |
|---|---|---|
| FastAPI | `>=0.115,<0.116` | MIT |
| Uvicorn | `>=0.30,<1` | BSD-3-Clause |
| Pydantic | `>=2.7,<3` | MIT |
| ruamel.yaml | `>=0.18,<0.19` | MIT |
| google-antigravity | `==0.1.22` | Apache-2.0 |
| pypdfium2 | `>=5,<6` | BSD-3-Clause / Apache-2.0 with bundled dependency licenses |

The locked transitive set is dominated by MIT, Apache-2.0, and BSD-family
licenses. It includes MPL-2.0 file-level components (`certifi`, `pathspec`) and
the `pypdfium2` wheel's bundled dependency/data licenses, including CC-BY-4.0.
A more detailed license inventory is maintained in the private development
repository; it is not part of this source distribution or the release archive.

Because package bodies are downloaded rather than redistributed, recipients
obtain each package's own license files through `uv`/the package index.

## Frontend dependencies

The release archive contains a production frontend build produced by Vite from
`frontend/package.json` and `frontend/package-lock.json`. Development
dependencies and `node_modules` are not included.

License files for the production frontend packages bundled into `frontend/dist`
are included in the archive under:

```text
licenses/frontend/<package>/LICENSE*
```

The frontend production closure includes React, React DOM, and their small
runtime dependency closure under permissive licenses (principally MIT). The
locked development closure contains MIT, ISC, Apache-2.0, BSD-family, MIT-0, and
CC-BY-4.0 entries (for browser data such as `caniuse-lite`); those development
packages are not distributed in the archive.

## Generated artwork and media

No model weights, embedding models, OCR models, media samples, or third-party
datasets are included in the release archive.

## Development references

The development repository references Olav OS and Olav Tasks for design and
process comparison; those projects are not runtime dependencies and are not
included in the release archive. No restricted reference implementation is
redistributed here.
