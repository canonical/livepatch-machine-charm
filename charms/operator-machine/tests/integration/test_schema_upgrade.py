import logging

import integration.utils as utils
import pytest
from juju.action import Action
from pytest_operator.plugin import OpsTest

LOGGER = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("deploy_built_bundle")
class TestSchemaUpgrade:
    async def test_it_blocks_when_no_schema_upgrade_ran(self, ops_test: OpsTest):
        # Checking postgres is active, livepatch blocked, and relation complete
        # means we should be at schema upgrade stage.
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(apps=["postgresql"], status="active")
            await ops_test.model.wait_for_idle(apps=["livepatch-machine"], status="blocked")

        # Relate so we can get to schema upgrade request
        await ops_test.model.add_relation("livepatch-machine:db", "postgresql:db")
        # TODO: Alex, after this relation it is going into "Livepatch is not running" state. Fix it.
        # The error is
        # unit-livepatch-machine-0: 10:22:28 INFO unit.livepatch-machine/0.juju-log db:3: Database has been migrated.
        # Current version: Error: failed to connect to `host=10.16.149.178 user=relation-3 database=livepatch`: server error # noqa: E501
        # (FATAL: unrecognized configuration parameter "fallback_application_name" (SQLSTATE 42704))
        # failed to connect to `host=10.16.149.178 user=relation-3 database=livepatch`: server error
        # (FATAL: unrecognized configuration parameter "fallback_application_name" (SQLSTATE 42704)
        # Wait for schema-upgrade request
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(apps=["postgresql"], status="active")
            await ops_test.model.wait_for_idle(apps=["livepatch-machine"], status="blocked")

        # Test it expects a schema upgrade to be run
        livepatch_unit = await utils.get_unit_by_name("livepatch-machine", "0", ops_test.model.units)
        assert livepatch_unit.workload_status == "blocked"
        expected = "Waiting for postgres relation to be established."
        got = livepatch_unit.workload_status_message
        assert expected == got

    async def test_schema_upgrade_runs_successfully(self, ops_test: OpsTest):
        # Checking postgres is active, livepatch blocked, and relation complete
        # means we should be at schema upgrade stage.
        async with ops_test.fast_forward():
            await ops_test.model.wait_for_idle(apps=["postgresql"], status="active")
            await ops_test.model.wait_for_idle(apps=["livepatch-machine"], status="blocked")

        await ops_test.model.add_relation("livepatch-machine:db", "postgresql:db")

        ops_test.model.get_action_output
        ops_test.model.wait_for_action

        livepatch_unit = await utils.get_unit_by_name("livepatch-machine", "0", ops_test.model.units)
        action: Action = await livepatch_unit.run_action("schema-upgrade")
        await action.wait()

        assert ops_test.model.applications["livepatch-machine"].status == "active"
        assert ops_test.model.applications["postgresql"].status == "active"
