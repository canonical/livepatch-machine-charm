#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration tests."""

import logging
from urllib.parse import urljoin

import pytest
import requests
from integration.conftest import deploy  # noqa: F401, pylint: disable=W0611
from integration.helpers import (
    APP_NAME,
    HAPROXY_NAME,
    get_unit_url,
    scale,
    simulate_charm_redeploy,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy")
class TestDeployment:
    """Integration tests for charm."""

    async def assert_http(
        self, ops_test: OpsTest, protocol: str, application: str, unit: int, port: int, path: str = ""
    ):
        """Call given HTTP endpoint and assert if the call was successful (HTTP 200)"""
        unit_url = await get_unit_url(ops_test, protocol=protocol, application=application, unit=unit, port=port)
        u = urljoin(unit_url, path)
        logger.info("curling app address: %s", u)
        response = requests.get(u, timeout=300, verify=False)  # nosec
        assert response.status_code == 200

    async def assert_livepatch_server_healthy(self, ops_test: OpsTest, unit: int = 0):
        """Perform `GET debug/status`request on the Livepatch unit."""
        await self.assert_http(
            ops_test,
            protocol="http",
            application=APP_NAME,
            unit=unit,
            port=8080,
            path="debug/status",
        )

    async def assert_ha_proxy_healthy(self, ops_test: OpsTest, unit: int = 0):
        """Perform `GET debug/status`request on HAProxy unit."""
        await self.assert_http(
            ops_test,
            protocol="http",
            application=HAPROXY_NAME,
            unit=unit,
            port=80,
            path="debug/status",
        )

    async def test_livepatch_server(self, ops_test: OpsTest):
        """Assert Livepatch server (unit=0) is healthy."""
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)

    async def test_charm_crash(self, ops_test: OpsTest):
        """Test backup and restore functionality.

        This should validate that the Superset charm itself is stateless
        and relies only on the postgreSQL database to store its chart values.
        """
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)
        await simulate_charm_redeploy(ops_test)
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)

    async def test_scale_up_and_down(self, ops_test: OpsTest):
        """Scale the livepatch machine charm up and then down."""
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)
        await scale(application_name=APP_NAME, ops_test=ops_test, count=2)
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_livepatch_server_healthy(ops_test, unit=1)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)
        await scale(application_name=APP_NAME, ops_test=ops_test, count=1)
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)
