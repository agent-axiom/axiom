"""Embedded build metadata.

The release workflow may overwrite this file before packaging so `axiom version
--verbose` remains useful outside a git checkout.
"""

VERSION = "0.1.0"
GIT_COMMIT = "unknown"
GIT_TAG = "development"
BUILD_TIMESTAMP = "development"
SOURCE_REPO = "https://github.com/agent-axiom/axiom"
