# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Integration tests for relations."""

import logging

import pytest
from integration import utils
from pytest_operator.plugin import OpsTest

LOGGER = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy_built_bundle")
@pytest.mark.skip
class TestRelations:
    """Class for testing charm relations."""

    async def test_it_waits_for_relation(self, ops_test: OpsTest):
        """Test that the charm waits for the relation."""
        # Wait for the units to enter idle state, with particular statuses
        # such that we can test the workload messages.
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(apps=["livepatch-machine"], status="blocked")

        # Test it expects a relation to occur
        livepatch_unit = await utils.get_unit_by_name("livepatch-machine", "0", ops_test.model.units)
        assert livepatch_unit.workload_status == "blocked"
        expected = "Waiting for postgres relation to be established."
        got = livepatch_unit.workload_status_message
        assert expected == got

    async def test_it_informs_users_of_waiting_for_postgres_primary_node_when_legacy_db_relation_is_integrated(
        self, ops_test: OpsTest
    ):
        """Test that charm informs users of waiting for postgres primary node when legacy db relation is integrated."""
        # Grab unit
        livepatch_unit = await utils.get_unit_by_name("livepatch-machine", "0", ops_test.model.units)

        # Relate these bad boys
        await ops_test.model.add_relation("livepatch-machine:database-legacy", "postgresql:db")

        # Push to first waiting status
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(apps=["livepatch-machine"], status="waiting")
        # Test livepatch wants the primary node selected
        expected = "Waiting for postgres to select primary node..."
        got = livepatch_unit.workload_status_message
        assert expected == got

    async def test_it_informs_users_of_waiting_for_postgres_when_database_relation_is_integrated(
        self, ops_test: OpsTest
    ):
        """Test that charm informs users that it is waiting for postgres when the database relation in integrated."""
        # Grab unit
        livepatch_unit = await utils.get_unit_by_name("livepatch-machine", "0", ops_test.model.units)

        # Relate these bad boys
        await ops_test.model.add_relation("livepatch-machine:database", "postgresql:database")

        # Push to first waiting status
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(apps=["livepatch-machine"], status="waiting")
        # Test livepatch is waiting for relation data from postgres
        expected = "Waiting for postgres...1"
        got = livepatch_unit.workload_status_message
        assert expected == got
