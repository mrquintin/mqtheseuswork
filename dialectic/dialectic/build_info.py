"""Build metadata embedded into Dialectic release bundles.

The CI and local packaging scripts overwrite these constants immediately before
PyInstaller runs. Development checkouts keep the empty defaults and fall back to
``git rev-parse HEAD`` at runtime.
"""

BUILD_VERSION = "0.1.0"
BUILD_COMMIT = ""
BUILD_ID = ""
BUILD_SOURCE = "development"
