#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Livepatch machine charm integration test helpers."""

import logging
from pathlib import Path

import yaml
from integration.utils import fetch_charm
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
POSTGRES_NAME = "postgresql"
HAPROXY_NAME = "haproxy"
NGINX_NAME = "nginx-ingress-integrator"


async def scale(ops_test: OpsTest, app, units):
    """Scale the application to the provided number and wait for idle.

    Args:
        ops_test: PyTest object.
        app: Application to be scaled.
        units: Number of units required.
    """
    await ops_test.model.applications[app].scale(scale=units)

    # Wait for model to settle
    await ops_test.model.wait_for_idle(
        apps=[app],
        status="active",
        idle_period=30,
        raise_on_blocked=True,
        timeout=300,
        wait_for_exact_units=units,
    )

    assert len(ops_test.model.applications[app].units) == units


async def get_unit_url(ops_test: OpsTest, application, unit, port, protocol="http"):
    """Returns unit URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        unit: Number of the unit.
        port: Port number of the URL.
        protocol: Transfer protocol (default: http).

    Returns:
        Unit URL of the form {protocol}://{address}:{port}
    """
    # Sometimes get_unit_address returns a None, no clue why, so looping until it's not
    url = await ops_test.model.applications[application].units[unit].get_public_address()
    return f"{protocol}://{url}:{port}"


async def get_unit_message(ops_test: OpsTest, application, unit) -> str:
    """Returns unit URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        unit: Number of the unit.

    Returns:
        The unit message
    """
    return ops_test.model.applications[application].units[unit].workload_status_message


async def simulate_charm_redeploy(ops_test: OpsTest):
    """Simulates the Livepatch charm being re-deployed.

    Args:
        ops_test: PyTest object.
    """
    await ops_test.model.applications[APP_NAME].destroy(force=True)
    await ops_test.model.block_until(lambda: APP_NAME not in ops_test.model.applications)

    charm = await fetch_charm(ops_test)

    await ops_test.model.deploy(
        charm,
        application_name=APP_NAME,
        num_units=1,
        config={
            "patch-storage.type": "postgres",
            "server.url-template": "http://livepatch:8080/v1/patches/{filename}",
        },
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="blocked", raise_on_blocked=False, timeout=600)
        await perform_livepatch_integrations(ops_test)
        await ops_test.model.wait_for_idle(apps=[APP_NAME], status="active", raise_on_blocked=False, timeout=600)


async def perform_livepatch_integrations(ops_test: OpsTest):
    """Add relations between Livepatch charm, postgresql, Ubuntu-advantage, and HAProxy.

    Args:
        ops_test: PyTest object.
    """
    logger.info("Integrating Livepatch and Postgresql")
    await ops_test.model.integrate(f"{APP_NAME}:database", f"{POSTGRES_NAME}:database")

    def checker():
        return (
            "Waiting for postgres relation"
            not in ops_test.model.applications[APP_NAME].units[0].workload_status_message
        )

    await ops_test.model.block_until(checker)
    logger.info("Integrating Livepatch and haproxy")
    await ops_test.model.integrate(f"{APP_NAME}:website", HAPROXY_NAME)


async def restart_application(ops_test: OpsTest):
    """Restart Livepatch application.

    Args:
        ops_test: PyTest object.
    """
    action = await ops_test.model.applications[APP_NAME].units[0].run_action("restart")
    await action.wait()
