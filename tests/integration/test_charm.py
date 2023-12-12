#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration tests."""

import logging

import pytest
import requests
from integration.conftest import deploy  # noqa: F401, pylint: disable=W0611
from integration.helpers import (  # , simulate_charm_redeploy
    APP_NAME,
    get_unit_url,
    scale,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for charm."""

    async def test_scale_up_and_down(self, ops_test: OpsTest):
        """Scale the livepatch machine charm up and then down."""
        await scale(application_name=APP_NAME, ops_test=ops_test, count=2)
        await self.test_livepatch_server(ops_test, unit=0)
        await self.test_livepatch_server(ops_test, unit=1)
        await scale(application_name=APP_NAME, ops_test=ops_test, count=1)
        await self.test_livepatch_server(ops_test, unit=0)

    async def test_livepatch_server(self, ops_test: OpsTest, unit: int = 0):
        """Perform GET request on the Livepatch unit."""
        url = await get_unit_url(ops_test, application=APP_NAME, unit=unit, port=8080)
        logger.info("curling app address: %s", url)
        response = requests.get(url, timeout=300, verify=False)  # nosec
        assert response.status_code == 200

    # async def test_charm_crash(self, ops_test: OpsTest):
    #     """Test backup and restore functionality.

    #     This should validate that the Superset charm itself is stateless
    #     and relies only on the postgreSQL database to store its chart values.
    #     """
    #     await self.test_livepatch_server(ops_test)
    #     await simulate_charm_redeploy(ops_test)
    #     await self.test_livepatch_server(ops_test)
    #     return
