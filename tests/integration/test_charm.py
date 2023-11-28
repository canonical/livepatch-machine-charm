#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration tests."""

import logging

import pytest
import requests
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import (
    UI_NAME,
    delete_chart,
    get_access_token,
    get_chart_count,
    get_unit_url,
    restart_application,
    simulate_crash,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for charm."""

    async def test_ui(self, ops_test: OpsTest):
        """Perform GET request on the Superset UI host."""
        url = await get_unit_url(ops_test, application=UI_NAME, unit=0, port=8088)
        logger.info("curling app address: %s", url)

        response = requests.get(url, timeout=300, verify=False)  # nosec
        assert response.status_code == 200

    async def test_charm_crash(self, ops_test: OpsTest):
        """Test backup and restore functionality.

        This should validate that the Superset charm itself is stateless
        and relies only on the postgreSQL database to store its chart values.
        """
        url = await get_unit_url(ops_test, application=UI_NAME, unit=0, port=8088)
        headers = await get_access_token(ops_test, url)

        # Delete a chart
        original_charts = await get_chart_count(ops_test, url, headers)
        await delete_chart(ops_test, url, headers)

        await simulate_crash(ops_test)

        # Get chart count on re-deployment
        url = await get_unit_url(ops_test, application=UI_NAME, unit=0, port=8088)
        chart_count = await get_chart_count(ops_test, url, headers)

        # Validate chart remains deleted
        logger.info("Validating state remains unchanged")
        assert chart_count == original_charts - 1

    async def test_restart_action(self, ops_test: OpsTest):
        """Restarts Superset application."""
        await restart_application(ops_test)
        assert ops_test.model.applications[UI_NAME].units[0].workload_status == "maintenance"


#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Temporal charm integration tests."""

import logging

import pytest
import requests
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import (
    APP_NAME,
    APP_NAME_UI,
    get_application_url,
    get_unit_url,
    run_sample_workflow,
    simulate_charm_crash,
)
from pytest_operator.plugin import OpsTest
from temporal_client.workflows import GreetingWorkflow
from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Temporal charm."""

    async def test_ui_relation(self, ops_test: OpsTest):
        """Perform GET request on the Temporal UI host."""
        url = await get_unit_url(ops_test, application=APP_NAME_UI, unit=0, port=8080)
        logger.info("curling app address: %s", url)

        response = requests.get(url, timeout=300)
        assert response.status_code == 200

    async def test_basic_client(self, ops_test: OpsTest):
        """Connects a client and runs a basic Temporal workflow."""
        await run_sample_workflow(ops_test)

    async def test_charm_crash(self, ops_test: OpsTest):
        """Test backup and restore functionality.

        This tests the charm's ability to continue workflow execution after simulating
        a crash in the charm. Essentially, it should prove that the charm is stateless
        and relies only on the db to store its workflow execution status.
        """
        url = await get_application_url(ops_test, application=APP_NAME, port=7233)
        logger.info("running signal workflow on app address: %s", url)

        client = await Client.connect(url)

        # Run a worker for the workflow
        async with Worker(
            client,
            task_queue="hello-signal-task-queue",
            workflows=[GreetingWorkflow],
        ):
            # While the worker is running, use the client to start the workflow.
            # Note, in many production setups, the client would be in a completely
            # separate process from the worker.
            handle = await client.start_workflow(
                GreetingWorkflow.run,
                id="hello-signal-workflow-id",
                task_queue="hello-signal-task-queue",
            )

            # Send a few signals for names, then signal it to exit
            await handle.signal(GreetingWorkflow.submit_greeting, "user1")
            await handle.signal(GreetingWorkflow.submit_greeting, "user2")
            await handle.signal(GreetingWorkflow.submit_greeting, "user3")

            await simulate_charm_crash(ops_test)

            url = await get_application_url(ops_test, application=APP_NAME, port=7233)

            new_client = await Client.connect(url)
            handle = new_client.get_workflow_handle("hello-signal-workflow-id")

            async with Worker(
                new_client,
                task_queue="hello-signal-task-queue",
                workflows=[GreetingWorkflow],
            ):
                await handle.signal(GreetingWorkflow.submit_greeting, "user4")
                await handle.signal(GreetingWorkflow.exit)

                # Show result
                result = await handle.result()
                logger.info(f"Signal Result: {result}")
                assert result == ["Hello, user1", "Hello, user2", "Hello, user3", "Hello, user4"]


#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Trino charm integration tests."""

import logging

import pytest
import requests
from conftest import deploy  # noqa: F401, pylint: disable=W0611
from helpers import (
    APP_NAME,
    CONN_CONFIG,
    CONN_NAME,
    TRINO_USER,
    get_catalogs,
    get_unit_url,
    run_connector_action,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for Trino charm."""

    async def test_trino_ui(self, ops_test: OpsTest):
        """Perform GET request on the Trino UI host."""
        url = await get_unit_url(ops_test, application=APP_NAME, unit=0, port=8080)
        logger.info("curling app address: %s", url)

        response = requests.get(url, timeout=300, verify=False)  # nosec
        assert response.status_code == 200

    async def test_basic_client(self, ops_test: OpsTest):
        """Connects a client and executes a basic SQL query."""
        catalogs = await get_catalogs(ops_test, TRINO_USER, APP_NAME)
        logging.info(f"trino catalogs: {catalogs}")
        assert catalogs

    async def test_add_connector_action(self, ops_test: OpsTest):
        """Adds a PostgreSQL connector and confirms database added."""
        params = {
            "conn-name": CONN_NAME,
            "conn-config": CONN_CONFIG,
        }
        catalogs = await run_connector_action(
            ops_test,
            "add-connector",
            params,
            TRINO_USER,
        )
        assert [CONN_NAME] in catalogs

    async def test_remove_connector_action(self, ops_test: OpsTest):
        """Removes an existing connector confirms database removed."""
        params = {
            "conn-name": CONN_NAME,
        }
        catalogs = await run_connector_action(
            ops_test,
            "remove-connector",
            params,
            TRINO_USER,
        )
        assert [CONN_NAME] not in catalogs
