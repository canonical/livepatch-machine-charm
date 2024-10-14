#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration tests."""

import json
import logging
from urllib.parse import urljoin

import pytest
import requests
from integration.conftest import deploy  # noqa: F401, pylint: disable=W0611
from integration.helpers import (
    APP_NAME,
    HAPROXY_NAME,
    PRO_AIRGAPPED_SERVER_NAME,
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

    async def assert_http(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, ops_test: OpsTest, protocol: str, application: str, unit: int, port: int, path: str = ""
    ) -> str:
        """
        Call given HTTP endpoint and assert if the call was successful (HTTP 200)

        The method returns the response body as a string.
        """
        unit_url = await get_unit_url(ops_test, protocol=protocol, application=application, unit=unit, port=port)
        u = urljoin(unit_url, path)
        logger.info("curling app address: %s", u)
        response = requests.get(u, timeout=300, verify=False)  # nosec
        assert response.status_code == 200
        return response.content.decode()

    async def assert_livepatch_server_healthy(self, ops_test: OpsTest, unit: int = 0) -> dict:
        """
        Perform `GET debug/status`request on the Livepatch unit.

        The method returns the HTTP response as a dict.
        """
        result = await self.assert_http(
            ops_test,
            protocol="http",
            application=APP_NAME,
            unit=unit,
            port=8080,
            path="debug/status",
        )
        return json.loads(result)

    async def assert_ha_proxy_healthy(self, ops_test: OpsTest, unit: int = 0) -> dict:
        """
        Perform `GET debug/status`request on HAProxy unit.

        The method returns the HTTP response as a dict.
        """
        result = await self.assert_http(
            ops_test,
            protocol="http",
            application=HAPROXY_NAME,
            unit=unit,
            port=80,
            path="debug/status",
        )
        return json.loads(result)

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

    async def test_integration_with_pro_airgapped_server(self, ops_test: OpsTest):
        """Test integration with pro-airgapped-server."""
        await self.assert_livepatch_server_healthy(ops_test, unit=0)
        await self.assert_ha_proxy_healthy(ops_test, unit=0)

        async with ops_test.fast_forward():
            await ops_test.model.deploy(
                PRO_AIRGAPPED_SERVER_NAME,
                num_units=1,
                config={
                    # Since we don't have a fake yet valid Pro token, we use the following
                    # override mechanism to bypass the validation step. The config below is
                    # taken from happy-path tests of the underlying project.
                    "manual-server-config": "QzE0TFpDQXh6MzZ3Nk5oNUVRRHVENmNtTkt0d1duOgogIGFjY291bnRJbmZvOgogICAgY3JlYXRlZEF0OiAiMjAyMi0wNS0xMlQwNjoyNzowM1oiCiAgICBpZDogYUFQWXc3M3hHCiAgICBuYW1lOiBhLmJAZXhhbXBsZS5jb20KICAgIHR5cGU6IHBlcnNvbmFsCiAgY29udHJhY3RJbmZvOgogICAgYWxsb3dhbmNlczoKICAgIC0gbWV0cmljOiB1bml0cwogICAgICB2YWx1ZTogMwogICAgY3JlYXRlZEF0OiAiMjAyMi0wNS0xMlQwNjoyNzowNFoiCiAgICBjcmVhdGVkQnk6ICIiCiAgICBlZmZlY3RpdmVGcm9tOiAiMjAyMi0wNS0xMlQwNjoyNzowNFoiCiAgICBlZmZlY3RpdmVUbzogIjk5OTktMTItMzFUMDA6MDA6MDBaIgogICAgaWQ6IGNBWC0tb05kCiAgICBpdGVtczoKICAgIC0gY29udHJhY3RJRDogY0FYLS1vTmQKICAgICAgY3JlYXRlZDogIjIwMjItMDUtMTJUMDY6Mjc6MDRaIgogICAgICBlZmZlY3RpdmVGcm9tOiAiMjAyMi0wNS0xMlQwNjoyNzowNFoiCiAgICAgIGVmZmVjdGl2ZVRvOiAiOTk5OS0xMi0zMVQwMDowMDowMFoiCiAgICAgIGV4dGVybmFsSURzOiBudWxsCiAgICAgIGlkOiAzOTYyOTAKICAgICAgbGFzdE1vZGlmaWVkOiAiMjAyMi0wNS0xMlQwNjoyNzowNFoiCiAgICAgIG1ldHJpYzogdW5pdHMKICAgICAgcmVhc29uOiBjb250cmFjdF9jcmVhdGVkCiAgICAgIHZhbHVlOiAzCiAgICBuYW1lOiBhLmJAZXhhbXBsZS5jb20KICAgIG9yaWdpbjogZnJlZQogICAgcHJvZHVjdHM6CiAgICAtIGZyZWUKICAgIHJlc291cmNlRW50aXRsZW1lbnRzOgogICAgLSBhZmZvcmRhbmNlczoKICAgICAgICBhcmNoaXRlY3R1cmVzOgogICAgICAgIC0gYW1kNjQKICAgICAgICAtIHg4Nl82NAogICAgICAgIHNlcmllczoKICAgICAgICAtIHhlbmlhbAogICAgICAgIC0gYmlvbmljCiAgICAgIGRpcmVjdGl2ZXM6CiAgICAgICAgYWRkaXRpb25hbFBhY2thZ2VzOgogICAgICAgIC0gdWJ1bnR1LWNvbW1vbmNyaXRlcmlhCiAgICAgICAgYXB0S2V5OiA5RjkxMkRBREQ5OUVFMUNDNkJGRkZGMjQzQTE4NkU3MzNGNDkxQzQ2CiAgICAgICAgYXB0VVJMOiBodHRwczovL2VzbS51YnVudHUuY29tL2NjCiAgICAgICAgc3VpdGVzOgogICAgICAgIC0geGVuaWFsCiAgICAgICAgLSBiaW9uaWMKICAgICAgZW50aXRsZWQ6IHRydWUKICAgICAgb2JsaWdhdGlvbnM6CiAgICAgICAgZW5hYmxlQnlEZWZhdWx0OiBmYWxzZQogICAgICB0eXBlOiBjYy1lYWw=",  # noqa: E501
                },
            )
            logger.info("Waiting for pro-airgapped-server")
            await ops_test.model.wait_for_idle(
                apps=[PRO_AIRGAPPED_SERVER_NAME], status="active", raise_on_blocked=False, timeout=600
            )
            logger.info("Integrating Livepatch and pro-airgapped-server")
            await ops_test.model.integrate(
                f"{APP_NAME}:pro-airgapped-server", f"{PRO_AIRGAPPED_SERVER_NAME}:livepatch-server"
            )
            logger.info("Waiting for Livepatch")
            await ops_test.model.wait_for_idle(
                apps=[APP_NAME, PRO_AIRGAPPED_SERVER_NAME], status="active", raise_on_blocked=False, timeout=600
            )

        status = await self.assert_ha_proxy_healthy(ops_test, unit=0)
        assert status["contracts"]["status"] == "OK"
