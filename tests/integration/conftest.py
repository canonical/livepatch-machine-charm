# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests configuration helpers and fixtures."""
import asyncio
import logging
from pathlib import Path

import pytest
import pytest_asyncio
from integration.helpers import (
    APP_NAME,
    HAPROXY_NAME,
    POSTGRES_NAME,
    UBUNTU_ADV_NAME,
    perform_livepatch_integrations,
    perform_other_components_integrations,
)
from integration.utils import fetch_charm
from pytest_operator.plugin import OpsTest

LOGGER = logging.getLogger(__name__)


@pytest.fixture(name="charm_path", scope="module")
async def build_charm_fixture(ops_test: OpsTest):
    """A fixture to Build the charm."""
    LOGGER.info("Building charm.")
    charm_path = await fetch_charm(ops_test)
    yield charm_path


@pytest.fixture(name="bundle_path", scope="module")  # charm_path: str)
def render_bundle_fixture(ops_test: OpsTest, charm_path: str):
    """Render bundle fixture."""
    LOGGER.info("Rendering bundle with snap and charm paths.")
    charm_directory = Path.cwd()
    tests_directory = charm_directory.joinpath("tests")
    tests_data_directory = tests_directory.joinpath("data")
    bundle_path = tests_data_directory.joinpath("int-test-bundle.yaml")

    rendered_bundle_path = ops_test.render_bundle(
        bundle_path,
        charm_path=charm_path,
    )
    LOGGER.info("Bundle path is: %s", str(rendered_bundle_path.absolute()))
    yield rendered_bundle_path


@pytest.mark.skip_if_deployed
@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest):
    """Deploy the charm."""
    charm = await ops_test.build_charm(".")
    common_constraints = {
        "cpu-cores": 1,
        "mem": 2048,
        "root-disk": 51200,
    }
    jammy = "jammy"
    async with ops_test.fast_forward():
        asyncio.gather(
            await ops_test.model.deploy(
                charm,
                application_name=APP_NAME,
                num_units=1,
                constraints=common_constraints,
                config={"patch-storage.type": "postgres"},
                series=jammy,
            ),
            await ops_test.model.deploy(
                POSTGRES_NAME,
                channel="14/stable",
                trust=True,
                constraints=common_constraints,
                num_units=1,
                series=jammy,
            ),
            await ops_test.model.deploy(
                HAPROXY_NAME,
                num_units=1,
                constraints=common_constraints,
                config={},
                series=jammy,
            ),
            await ops_test.model.deploy(
                UBUNTU_ADV_NAME,
                num_units=1,
                config={"ppa": "ppa:ua-client/stable"},
                series=jammy,
            ),
        )

    async with ops_test.fast_forward():
        # wait for deployment to be done
        # TODO(mina1460): Do we need to wait for HAPROXY and ubuntu-advantage?
        await ops_test.model.wait_for_idle(apps=[POSTGRES_NAME], status="active", raise_on_blocked=False, timeout=600)
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", raise_on_blocked=False, timeout=600)
        await ops_test.model.wait_for_idle(
            apps=[HAPROXY_NAME, UBUNTU_ADV_NAME], status="active", raise_on_blocked=False, timeout=600
        )
        # add relations
        await perform_livepatch_integrations(ops_test)
        await perform_other_components_integrations(ops_test)
        # wait for app to be active
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=300)
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
    return
