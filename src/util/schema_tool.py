# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Schema tool action."""

import subprocess  # nosec

from constants.snap import (
    SCHEMA_UPGRADE_COMMAND,
    SCHEMA_VERSION_CHECK,
    SERVER_SNAP_NAME,
)


def run_schema_version_check(master_uri: str) -> str:
    """Run a schema version check against the database."""
    _cmd = [f"{SERVER_SNAP_NAME}.{SCHEMA_VERSION_CHECK}", master_uri]
    result = "failed"
    try:
        result = subprocess.check_output(_cmd, universal_newlines=True, stderr=subprocess.STDOUT)  # nosec

    except subprocess.CalledProcessError as e:
        result = e.output
    return result


def run_schema_upgrade(master_uri: str) -> str:
    """Run a schema upgrade against the desired Postgres URI."""
    _cmd = [
        f"{SERVER_SNAP_NAME}.{SCHEMA_UPGRADE_COMMAND}",
        master_uri,
    ]
    result = "failed"
    try:
        result = subprocess.check_output(_cmd, universal_newlines=True, stderr=subprocess.STDOUT)  # nosec

    except subprocess.CalledProcessError as e:
        result = e.output
    return result
