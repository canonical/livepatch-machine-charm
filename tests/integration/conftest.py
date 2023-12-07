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
    get_unit_url,
    perform_livepatch_integrations,
)
from integration.utils import fetch_charm
from pytest_operator.plugin import OpsTest

LOGGER = logging.getLogger(__name__)


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
    charm = await fetch_charm(ops_test)
    jammy = "ubuntu@22.04"
    asyncio.gather(
        ops_test.model.deploy(
            charm,
            application_name=APP_NAME,
            num_units=1,
            config={"patch-storage.type": "postgres"},
            base=jammy,
        ),
        ops_test.model.deploy(
            POSTGRES_NAME,
            channel="14/stable",
            num_units=1,
            base=jammy,
        ),
        ops_test.model.deploy(
            HAPROXY_NAME,
            num_units=1,
            config={},
            base=jammy,
        ),
    )

    async with ops_test.fast_forward():
        # wait for deployment to be done
        LOGGER.info("Waiting for Postgresql")
        await ops_test.model.wait_for_idle(apps=[POSTGRES_NAME], status="active", raise_on_blocked=False, timeout=600)
        LOGGER.info("Waiting for Livepatch")
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", raise_on_blocked=False, timeout=600)
        LOGGER.info("Waiting for HAProxy")
        await ops_test.model.wait_for_idle(apps=[HAPROXY_NAME], status="active", raise_on_blocked=False, timeout=600)
        LOGGER.info("Setting server.url-template")
        url = await get_unit_url(ops_test, application=HAPROXY_NAME, unit=0, port=80)
        url_template = url + "/v1/patches/{filename}"
        LOGGER.info(f"Set server.url-template to {url_template}")
        await ops_test.model.applications[APP_NAME].set_config({"server.url-template": url_template})
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", raise_on_blocked=False, timeout=300)
        LOGGER.info("Check for blocked waiting on DB relation")
        message = ops_test.model.applications[APP_NAME].units[0].workload_status_message
        assert message == "Waiting for postgres relation to be established."
        LOGGER.info("Making relations")
        await perform_livepatch_integrations(ops_test)
        LOGGER.info("Check for blocked waiting on DB migration")
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", raise_on_blocked=False, timeout=300)
        LOGGER.info("Running migration action")
        action = await ops_test.model.applications[APP_NAME].units[0].run_action("schema-upgrade")
        action = await action.wait()
        assert action.results["schema-upgrade-required"] == "False"
        LOGGER.info("Waiting for active idle")
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=300)
        assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
    return
