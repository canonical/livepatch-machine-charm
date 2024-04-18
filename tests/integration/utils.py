# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
"""Utilities for integration tests."""

import glob
import logging
from pathlib import Path
from typing import Dict

from juju.unit import Unit
from pytest_operator.plugin import OpsTest

LOGGER = logging.getLogger(__name__)


async def get_unit_by_name(unit_name: str, unit_index: str, unit_list: Dict[str, Unit]) -> Unit:
    """Return the unit by its name and index"""
    return unit_list.get(f"{unit_name}/{unit_index}")


async def fetch_charm(ops_test: OpsTest) -> str:
    """Use an existing charm in the directory or builds the charm if it doesn't exist."""
    LOGGER.info("Building charm...")
    try:
        charm_path = Path(get_local_charm()).resolve()
        LOGGER.info("Skipping charm build. Found existing charm.")
    except FileNotFoundError:
        charm_path = await ops_test.build_charm(".")
    LOGGER.info("Charm path is: %s", charm_path)
    return str(charm_path)


def get_local_charm():
    """gets local files with .charm extension."""
    charm = glob.glob("./*.charm")
    if len(charm) != 1:
        raise FileNotFoundError(f"Found {len(charm)} file(s) with .charm extension.")
    return charm[0]
