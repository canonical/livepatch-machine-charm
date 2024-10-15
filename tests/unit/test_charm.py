# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing
"""Unit tests module."""
import os
import tempfile
import unittest
from typing import Any, Dict, List
from unittest.mock import Mock, patch

import yaml
from ops.model import StatusBase
from ops.testing import ActionFailed, Harness

import src.charm

APP_NAME = "canonical-livepatch-server"


# pylint: disable=too-many-public-methods
class TestCharm(unittest.TestCase):
    """Unit tests class."""

    def setUp(self):
        self.harness = Harness(src.charm.OperatorMachineCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.disable_hooks()

        self.snap_mock, snap_cache_patch = self.new_mock_snap_cache()
        snap_cache_patch.start()
        self.addCleanup(snap_cache_patch.stop)

        self.harness.begin()

    def new_mock_snap_cache(self):
        """create a mock snap cache"""
        mock = Mock()
        snap_cache = {"canonical-livepatch-server": mock}
        return mock, patch("src.charm.SnapCache", return_value=snap_cache)

    def test_snap_config(self):
        """Test snap config is set as expected."""
        self.start_leader_unit()

        expected_config = {
            "lp.patch-sync.sync-tiers": True,
        }

        def snap_set_mock(prefixed_configuration: Dict[str, Any]):
            self.assertEqual(prefixed_configuration, prefixed_configuration | expected_config)

        self.snap_mock.set = Mock(side_effect=snap_set_mock)
        self.harness.update_config({"patch-sync.sync-tiers": True})
        self.assertTrue(self.snap_mock.set.called)

    # wokeignore:rule=master
    def test_legacy_db_master_changed(self):
        """test `_legacy_db_master_changed event` handler."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        legacy_db_rel_id = self.harness.add_relation("database-legacy", "postgres")

        # The `ops-lib-pgsql` library calls `leader-get` and `leader-set` tools
        # from juju help-tools, so we need to mock calls that try to spawn a
        # subprocess.
        stored_data = "'{}'"

        def set_database_name_using_juju_leader_set(cmd: List[str]):
            nonlocal stored_data
            self.assertEqual(cmd[0], "leader-set")
            self.assertTrue(cmd[1].startswith("interface.pgsql="))
            stored_data = yaml.safe_dump(cmd[1].removeprefix("interface.pgsql="))

        check_call_mock = Mock(side_effect=set_database_name_using_juju_leader_set)

        def get_database_name_using_juju_leader_get(cmd: List[str]):
            self.assertEqual(cmd[0], "leader-get")
            return bytes(stored_data, "utf-8")

        check_output_mock = Mock(side_effect=get_database_name_using_juju_leader_get)

        with patch("subprocess.check_call", check_call_mock):  # Stubs `leader-set` call.
            with patch("subprocess.check_output", check_output_mock):  # Stubs `leader-get` call.
                self.harness.add_relation_unit(legacy_db_rel_id, "postgres/0")
                self.harness.update_relation_data(
                    legacy_db_rel_id,
                    "postgres/0",
                    {
                        "database": "livepatch",
                        # wokeignore:rule=master
                        "master": "host=host port=5432 dbname=livepatch user=username password=password",
                    },
                )

                self.assertEqual(self.harness.charm._state.db_uri, "postgresql://username:password@host:5432/livepatch")

    def test_legacy_db_standby_changed(self):
        """test `_legacy_db_standby_changed event` handler."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        legacy_db_rel_id = self.harness.add_relation("database-legacy", "postgres")

        # The `ops-lib-pgsql` library calls `leader-get` and `leader-set` tools
        # from juju help-tools, so we need to mock calls that try to spawn a
        # subprocess.
        stored_data = "'{}'"

        def set_database_name_using_juju_leader_set(cmd: List[str]):
            nonlocal stored_data
            self.assertEqual(cmd[0], "leader-set")
            self.assertTrue(cmd[1].startswith("interface.pgsql="))
            stored_data = yaml.safe_dump(cmd[1].removeprefix("interface.pgsql="))

        check_call_mock = Mock(side_effect=set_database_name_using_juju_leader_set)

        def get_database_name_using_juju_leader_get(cmd: List[str]):
            self.assertEqual(cmd[0], "leader-get")
            return bytes(stored_data, "utf-8")

        check_output_mock = Mock(side_effect=get_database_name_using_juju_leader_get)

        with patch("subprocess.check_call", check_call_mock):  # Stubs `leader-set` call.
            with patch("subprocess.check_output", check_output_mock):  # Stubs `leader-get` call.
                self.harness.add_relation_unit(legacy_db_rel_id, "postgres/0")
                self.harness.update_relation_data(
                    legacy_db_rel_id,
                    "postgres/0",
                    {
                        "database": "livepatch",
                        "standbys": "host=standby-host port=5432 dbname=livepatch user=username password=password",
                    },
                )

                self.assertEqual(
                    self.harness.charm._state.db_ro_uris, ["postgresql://username:password@standby-host:5432/livepatch"]
                )

    # wokeignore:rule=master
    def test_legacy_db_relation__both_master_and_standby(self):
        """test legacy db relation handlers' function when both primary and standby units are provided."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        legacy_db_rel_id = self.harness.add_relation("database-legacy", "postgres")

        # The `ops-lib-pgsql` library calls `leader-get` and `leader-set` tools
        # from juju help-tools, so we need to mock calls that try to spawn a
        # subprocess.
        stored_data = "'{}'"

        def set_database_name_using_juju_leader_set(cmd: List[str]):
            nonlocal stored_data
            self.assertEqual(cmd[0], "leader-set")
            self.assertTrue(cmd[1].startswith("interface.pgsql="))
            stored_data = yaml.safe_dump(cmd[1].removeprefix("interface.pgsql="))

        check_call_mock = Mock(side_effect=set_database_name_using_juju_leader_set)

        def get_database_name_using_juju_leader_get(cmd: List[str]):
            self.assertEqual(cmd[0], "leader-get")
            return bytes(stored_data, "utf-8")

        check_output_mock = Mock(side_effect=get_database_name_using_juju_leader_get)

        with patch("subprocess.check_call", check_call_mock):  # Stubs `leader-set` call.
            with patch("subprocess.check_output", check_output_mock):  # Stubs `leader-get` call.
                self.harness.add_relation_unit(legacy_db_rel_id, "postgres/0")
                self.harness.update_relation_data(
                    legacy_db_rel_id,
                    "postgres/0",
                    {
                        "database": "livepatch",
                        # wokeignore:rule=master
                        "master": "host=host port=5432 dbname=livepatch user=username password=password",
                    },
                )

                self.assertEqual(self.harness.charm._state.db_uri, "postgresql://username:password@host:5432/livepatch")

                self.harness.update_relation_data(
                    legacy_db_rel_id,
                    "postgres/0",
                    {
                        "database": "livepatch",
                        # wokeignore:rule=master
                        "master": "host=host port=5432 dbname=livepatch user=username password=password",
                        "standbys": "host=standby-host port=5432 dbname=livepatch user=username password=password",
                    },
                )

                self.assertEqual(
                    self.harness.charm._state.db_ro_uris, ["postgresql://username:password@standby-host:5432/livepatch"]
                )

    def test_database_relations_are_mutually_exclusive__legacy_first(self):
        """test db relations are mutually exclusive for legacy relations."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        legacy_db_rel_id = self.harness.add_relation("database-legacy", "postgres")

        # The `ops-lib-pgsql` library calls `leader-get` and `leader-set` tools
        # from juju help-tools, so we need to mock calls that try to spawn a
        # subprocess.
        with patch("subprocess.check_call", return_value=None):  # Stubs `leader-set` call.
            with patch("subprocess.check_output", return_value=b""):  # Stubs `leader-get` call.
                self.harness.add_relation_unit(legacy_db_rel_id, "postgres/0")
        self.harness.update_relation_data(legacy_db_rel_id, "postgres", {})

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        with self.assertRaises(Exception) as cm:
            self.harness.update_relation_data(
                db_rel_id,
                "postgres-new",
                {
                    "username": "some-username",
                    "password": "some-password",
                    "endpoints": "some.database.host,some.other.database.host",
                },
            )

        self.assertEqual(
            str(cm.exception),
            "Integration with both database relations is not allowed; `database-legacy` is already activated.",
        )

    def test_database_relations_are_mutually_exclusive__standard_first(self):
        """Test db relations are mutually exclusive."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        self.harness.update_relation_data(
            db_rel_id,
            "postgres-new",
            {
                "username": "some-username",
                "password": "some-password",
                "endpoints": "some.database.host,some.other.database.host",
            },
        )

        legacy_db_rel_id = self.harness.add_relation("database-legacy", "postgres")

        with self.assertRaises(Exception) as cm:
            # The `ops-lib-pgsql` library calls `leader-get` and `leader-set` tools
            # from juju help-tools, so we need to mock calls that try to spawn a
            # subprocess.
            with patch("subprocess.check_call", return_value=None):  # Stubs `leader-set` call.
                with patch("subprocess.check_output", return_value=b""):  # Stubs `leader-get` call.
                    self.harness.add_relation_unit(legacy_db_rel_id, "postgres/0")

        self.assertEqual(
            str(cm.exception),
            "Integration with both database relations is not allowed; `database` is already activated.",
        )

    def test_standard_database_relation__success(self):
        """Test standard db relation successfully integrates with database."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        self.harness.update_relation_data(
            db_rel_id,
            "postgres-new",
            {
                "username": "some-username",
                "password": "some-password",
                "endpoints": "some.database.host,some.other.database.host",
            },
        )

        self.assertEqual(
            self.harness.charm._state.db_uri,
            "postgresql://some-username:some-password@some.database.host/livepatch",
        )

    def test_website_relation__success(self):
        """Test website relation integrates successfully."""
        self.harness.update_config({"server.server-address": "some-host:9999"})

        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        rel_id = self.harness.add_relation("website", "reverse-proxy")
        self.harness.add_relation_unit(rel_id, "reverse-proxy/0")
        rel_data = self.harness.get_relation_data(rel_id, self.harness.charm.unit)

        self.assertEqual(rel_data["port"], "9999")

    def test_standard_database_relation__empty_username_or_password(self):
        """Test standard db relation does not update the db_uri if credentials are not set in relation data."""
        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)
        self.harness.enable_hooks()

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        self.harness.update_relation_data(
            db_rel_id,
            "postgres-new",
            {
                "username": "",
                "password": "",
                "endpoints": "some.database.host,some.other.database.host",
            },
        )

        # We should verify at this point the db_uri is not set in the state, as
        # this is perceived as an incomplete integration.
        self.assertIsNone(self.harness.charm._state.db_uri)

    def test_pro_airgapped_server_relation__success(self):
        """Test pro-airgapped-server relation."""
        self.start_leader_unit()

        expected_config = {
            "lp.contracts.enabled": True,
            "lp.contracts.url": "scheme://some.host.name:9999",
        }

        def snap_set_mock(prefixed_configuration: Dict[str, Any]):
            self.assertEqual(prefixed_configuration, prefixed_configuration | expected_config)
            self.assertNotIn("lp.contracts.user", prefixed_configuration)
            self.assertNotIn("lp.contracts.password", prefixed_configuration)

        self.snap_mock.set = Mock(side_effect=snap_set_mock)
        pro_rel_id = self.harness.add_relation("pro-airgapped-server", "pro-airgapped-server")
        self.harness.add_relation_unit(pro_rel_id, "pro-airgapped-server/0")
        self.harness.update_relation_data(
            pro_rel_id,
            "pro-airgapped-server/0",
            {
                "scheme": "scheme",
                "hostname": "some.host.name",
                "port": "9999",
            },
        )
        self.assertTrue(self.snap_mock.set.called)

    def test_pro_airgapped_server_relation__multiple_units(self):
        """Test pro-airgapped-server relation when there are multiple units."""
        self.start_leader_unit()

        def update_snap_set_mock(expected_enabled: bool, expected_url: str):
            expected_config = {
                "lp.contracts.enabled": expected_enabled,
                "lp.contracts.url": expected_url,
            }

            def snap_set_mock(prefixed_configuration: Dict[str, Any]):
                self.assertEqual(prefixed_configuration, prefixed_configuration | expected_config)
                self.assertNotIn("lp.contracts.user", prefixed_configuration)
                self.assertNotIn("lp.contracts.password", prefixed_configuration)

            self.snap_mock.set = Mock(side_effect=snap_set_mock)

        update_snap_set_mock(True, "scheme://first.host:9999")
        pro_rel_id = self.harness.add_relation("pro-airgapped-server", "pro-airgapped-server")
        self.harness.add_relation_unit(pro_rel_id, "pro-airgapped-server/0")
        self.harness.update_relation_data(
            pro_rel_id,
            "pro-airgapped-server/0",
            {
                "scheme": "scheme",
                "hostname": "first.host",
                "port": "9999",
            },
        )
        self.assertTrue(self.snap_mock.set.called)

        # Adding another unit of `pro-airgapped-server`, but this new unit should not
        # affect the Livepatch server configuration.
        update_snap_set_mock(True, "scheme://first.host:9999")
        self.harness.add_relation_unit(pro_rel_id, "pro-airgapped-server/1")
        self.harness.update_relation_data(
            pro_rel_id,
            "pro-airgapped-server/1",
            {
                "scheme": "scheme",
                "hostname": "second.host",
                "port": "9999",
            },
        )
        self.assertTrue(self.snap_mock.set.called)

    def test_pro_airgapped_server_relation__multiple_units_one_departs(self):
        """Test pro-airgapped-server relation when one of the relation units departs but the other one not."""
        self.start_leader_unit()

        def update_snap_set_mock(expected_enabled: bool, expected_url: str):
            expected_config = {
                "lp.contracts.enabled": expected_enabled,
                "lp.contracts.url": expected_url,
            }

            def snap_set_mock(prefixed_configuration: Dict[str, Any]):
                self.assertEqual(prefixed_configuration, prefixed_configuration | expected_config)
                self.assertNotIn("lp.contracts.user", prefixed_configuration)
                self.assertNotIn("lp.contracts.password", prefixed_configuration)

            self.snap_mock.set = Mock(side_effect=snap_set_mock)

        update_snap_set_mock(True, "scheme://first.host:9999")
        pro_rel_id = self.harness.add_relation("pro-airgapped-server", "pro-airgapped-server")
        self.harness.add_relation_unit(pro_rel_id, "pro-airgapped-server/0")
        self.harness.update_relation_data(
            pro_rel_id,
            "pro-airgapped-server/0",
            {
                "scheme": "scheme",
                "hostname": "first.host",
                "port": "9999",
            },
        )
        self.assertTrue(self.snap_mock.set.called)

        # Make sure adding another unit doesn't change the last contracts URL.
        update_snap_set_mock(True, "scheme://first.host:9999")
        self.harness.add_relation_unit(pro_rel_id, "pro-airgapped-server/1")
        self.harness.update_relation_data(
            pro_rel_id,
            "pro-airgapped-server/1",
            {
                "scheme": "scheme",
                "hostname": "second.host",
                "port": "9999",
            },
        )
        self.assertTrue(self.snap_mock.set.called)

        # Now we drop remove the first `pro-airgapped-server` unit. The charm should
        # use the second unit address.
        update_snap_set_mock(True, "scheme://second.host:9999")
        self.harness.remove_relation_unit(pro_rel_id, "pro-airgapped-server/0")
        self.assertTrue(self.snap_mock.set.called)

    def test_pro_airgapped_server_relation__relation_removed(self):
        """Test when pro-airgapped-server is removed."""
        self.start_leader_unit()

        pro_rel_id = self.harness.add_relation("pro-airgapped-server", "pro-airgapped-server")
        self.harness.add_relation_unit(pro_rel_id, "pro-airgapped-server/0")
        self.harness.update_relation_data(
            pro_rel_id,
            "pro-airgapped-server/0",
            {
                "scheme": "scheme",
                "hostname": "first.host",
                "port": "9999",
            },
        )

        expected_config = {
            "lp.contracts.enabled": False,
        }

        # Now we remove the relation. The charm should disable use of contracts.
        def snap_set_mock(prefixed_configuration: Dict[str, Any]):
            self.assertEqual(prefixed_configuration, prefixed_configuration | expected_config)

        self.snap_mock.set = Mock(side_effect=snap_set_mock)
        self.harness.remove_relation(pro_rel_id)
        self.assertTrue(self.snap_mock.set.called)

    def test_install(self):
        """test install event handler."""
        self.snap_mock.present = False
        self.snap_mock.services = {"livepatch": {"active": False}}
        self.snap_mock.ensure.return_value = None
        self.snap_mock.hold.return_value = None
        self.snap_mock.set.return_value = None
        self.snap_mock.restart.return_value = None

        def subprocess_check_output_side_effect(cmd: str, *args, **kwargs):
            if cmd[0] == "canonical-livepatch-server.check-schema-version":
                return "\n"
            if cmd[0] == "leader-get":
                return b""
            raise AssertionError("unexpected call")

        subprocess_check_output_mock = Mock(side_effect=subprocess_check_output_side_effect)
        schema_version_check_patch = patch("subprocess.check_output", subprocess_check_output_mock)
        self.addCleanup(schema_version_check_patch.stop)
        schema_version_check_patch.start()

        self.harness.enable_hooks()

        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)

        self.harness.charm.on.install.emit()

        self.assertEqual(self.harness.model.unit.status.message, "Snap installed! Waiting on postgres relation...")

    def test_install__already_installed(self):
        """test install event handler, when the livepatch snap is already installed."""
        self.snap_mock.present = True
        self.snap_mock.services = {"livepatch": {"active": False}}
        self.snap_mock.set.return_value = None
        self.snap_mock.restart.return_value = None

        def subprocess_check_output_side_effect(cmd: str, *args, **kwargs):
            if cmd[0] == "canonical-livepatch-server.check-schema-version":
                return "\n"
            if cmd[0] == "leader-get":
                return b""
            raise AssertionError("unexpected call")

        subprocess_check_output_mock = Mock(side_effect=subprocess_check_output_side_effect)
        schema_version_check_patch = patch("subprocess.check_output", subprocess_check_output_mock)
        self.addCleanup(schema_version_check_patch.stop)
        schema_version_check_patch.start()

        self.harness.enable_hooks()

        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)

        self.harness.charm.on.install.emit()

        self.assertEqual(self.harness.model.unit.status.message, "Livepatch snap already installed...")

    def start_leader_unit(self):
        """starts leader unit by doing a full configuration/integration."""
        self.snap_mock.present = True
        self.snap_mock.services = {"livepatch": {"active": False}}
        self.snap_mock.set.return_value = None
        self.snap_mock.restart.return_value = None

        def subprocess_check_output_side_effect(cmd: str, *args, **kwargs):
            if cmd[0] == "canonical-livepatch-server.check-schema-version":
                return "\n"
            if cmd[0] == "leader-get":
                return b""
            if cmd[0] == "update-ca-certificates":
                return b"updated-ca-certs"
            raise AssertionError("unexpected call")

        subprocess_check_output_mock = Mock(side_effect=subprocess_check_output_side_effect)
        schema_version_check_patch = patch("subprocess.check_output", subprocess_check_output_mock)
        self.addCleanup(schema_version_check_patch.stop)
        schema_version_check_patch.start()

        self.harness.enable_hooks()

        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        self.harness.update_relation_data(
            db_rel_id,
            "postgres-new",
            {
                "username": "some-username",
                "password": "some-password",
                "endpoints": "some.database.host,some.other.database.host",
            },
        )

        def set_snap_as_running(*args, **kwargs):
            self.snap_mock.services = {"livepatch": {"active": True}}

        self.snap_mock.restart.side_effect = set_snap_as_running

        self.harness.update_config({"server.url-template": "some-url-template"})

        self.assertEqual(self.harness.model.unit.status.message, "Livepatch running!")

    def test_update_status__running(self):
        """test `update-status` event handler."""
        self.start_leader_unit()

        self.harness.charm.on.update_status.emit()

        self.assertEqual(self.harness.model.unit.status.message, "Livepatch running!")

    def test_update_status__not_running_after_being_active(self):
        """test `update-status` event handler when service is not running (after it was being active)."""
        self.start_leader_unit()

        self.snap_mock.services = {"livepatch": {"active": False}}  # mark service as stopped

        self.harness.charm.on.update_status.emit()

        self.assertEqual(self.harness.model.unit.status.message, "Livepatch is not running.")
        self.assertEqual(self.harness.model.unit.status.name, "maintenance")

    def test_update_status__not_running_after_not_being_active(self):
        """test `update-status` event handler when service is not running (and wasn't running before)."""
        self.start_leader_unit()

        self.snap_mock.services = {"livepatch": {"active": False}}  # mark service as stopped

        class MockStatus(StatusBase):
            """Mock status class to make sure this type of status is unknown to the code."""

            name = "some fake status"

        self.harness.model.unit.status = MockStatus("some fake message")

        # We should verify that the state is not changed in this case.
        last_status_message = self.harness.model.unit.status.message
        last_status_name = self.harness.model.unit.status.name

        self.harness.charm.on.update_status.emit()

        self.assertEqual(self.harness.model.unit.status.message, last_status_message)
        self.assertEqual(self.harness.model.unit.status.name, last_status_name)

    def test_start(self):
        """test successfully running livepatch."""
        self.start_leader_unit()

    def test_enable_action__success(self):
        """test `enable` action."""
        self.start_leader_unit()
        self.snap_mock.get.return_value = "some-token"

        result = self.harness.run_action("enable", {"token": "some-token"})

        self.snap_mock.set.assert_called_with({"token": "some-token"})
        self.snap_mock.get.assert_called_with("token")
        self.assertEqual(result.results["enabled"], "true")

    def test_enable_action__empty_token(self):
        """test `enable` action when provided token is empty."""
        self.start_leader_unit()

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action("enable", {"token": ""})

        self.assertEqual(ex.exception.message, "No token provided.")

    def test_enable_action__empty_retrieved_token(self):
        """test `enable` action when provided token cannot be set in the snap's configuration."""
        self.start_leader_unit()
        self.snap_mock.get.return_value = ""  # retrieved token

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action("enable", {"token": "some-token"})

        self.assertEqual(ex.exception.message, "Failed to enable Ubuntu Pro, is your token correct?")

    def test_enable_action__snap_not_installed(self):
        """test `enable` action when livepatch snap is not installed."""
        self.snap_mock.present = False

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action("enable", {"token": "some-token"})

        self.assertEqual(ex.exception.message, "Livepatch snap is not installed.")

    def test_restart_action__success(self):
        """test `restart` action."""
        self.start_leader_unit()
        self.snap_mock.services = {"livepatch": {"active": False}}  # mark service as stopped

        def happy_restart(services: List[str], *args, **kwargs):
            self.snap_mock.services = {"livepatch": {"active": True}}

        self.snap_mock.restart = Mock(side_effect=happy_restart)

        result = self.harness.run_action("restart")

        self.snap_mock.restart.assert_called_with(["livepatch"])
        self.assertEqual(result.results["restarted"], "true")

    def test_restart_action__failed_restart(self):
        """test `restart` action when service is not running after restart."""
        self.start_leader_unit()
        self.snap_mock.services = {"livepatch": {"active": False}}  # mark service as stopped
        self.snap_mock.restart = Mock(return_value=None)

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action("restart", {})

        self.snap_mock.restart.assert_called_with(["livepatch"])
        self.assertEqual(ex.exception.message, "Server failed to restart.")

    def test_restart_action__snap_not_installed(self):
        """test `restart` action when snap is not installed."""
        self.start_leader_unit()
        self.snap_mock.present = False

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action("restart", {})

        self.assertEqual(
            ex.exception.message, "Livepatch server failed to restart, as the server snap is not installed."
        )

    def test_schema_upgrade_action__success(self):
        """test `schema-upgrade` action."""
        self.snap_mock.present = True
        self.snap_mock.services = {"livepatch": {"active": False}}
        self.snap_mock.set.return_value = None
        self.snap_mock.restart.return_value = None

        check_schema_version_check_output = "Error: database not initialized"

        def subprocess_check_output_side_effect(cmd: str, *args, **kwargs):
            if cmd[0] == "canonical-livepatch-server.check-schema-version":
                return check_schema_version_check_output
            if cmd[0] == "canonical-livepatch-server.schema-tool":
                return ""
            if cmd[0] == "leader-get":
                return b""
            raise AssertionError("unexpected call")

        subprocess_check_output_mock = Mock(side_effect=subprocess_check_output_side_effect)
        schema_version_check_patch = patch("subprocess.check_output", subprocess_check_output_mock)
        self.addCleanup(schema_version_check_patch.stop)
        schema_version_check_patch.start()

        self.harness.enable_hooks()

        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        self.harness.update_relation_data(
            db_rel_id,
            "postgres-new",
            {
                "username": "some-username",
                "password": "some-password",
                "endpoints": "some.database.host,some.other.database.host",
            },
        )

        self.harness.update_config({"server.url-template": "some-url-template"})

        self.assertEqual(
            self.harness.model.unit.status.message, "Database not initialised, please run the schema-upgrade action."
        )

        check_schema_version_check_output = "some-version"  # From now on, the database is migrated

        result = self.harness.run_action("schema-upgrade")

        self.assertListEqual(
            subprocess_check_output_mock.call_args.args[0],
            ["canonical-livepatch-server.check-schema-version", self.harness.charm._state.db_uri],
        )
        self.assertEqual(
            result.results,
            {
                "schema-upgrade-required": False,
                "schema-version": "some-version",
            },
        )

    def test_schema_upgrade_action__failed(self):
        """test `schema-upgrade` action failure."""
        self.snap_mock.present = True
        self.snap_mock.services = {"livepatch": {"active": False}}
        self.snap_mock.set.return_value = None
        self.snap_mock.restart.return_value = None

        check_schema_version_check_output = "Error: database not initialized"

        def subprocess_check_output_side_effect(cmd: str, *args, **kwargs):
            if cmd[0] == "canonical-livepatch-server.check-schema-version":
                return check_schema_version_check_output
            if cmd[0] == "canonical-livepatch-server.schema-tool":
                return ""
            if cmd[0] == "leader-get":
                return b""
            raise AssertionError("unexpected call")

        subprocess_check_output_mock = Mock(side_effect=subprocess_check_output_side_effect)
        schema_version_check_patch = patch("subprocess.check_output", subprocess_check_output_mock)
        self.addCleanup(schema_version_check_patch.stop)
        schema_version_check_patch.start()

        self.harness.enable_hooks()

        rel_id = self.harness.add_relation("livepatch", "livepatch")
        self.harness.add_relation_unit(rel_id, f"{APP_NAME}/1")
        self.harness.set_leader(True)

        db_rel_id = self.harness.add_relation("database", "postgres-new")
        self.harness.add_relation_unit(db_rel_id, "postgres-new/0")
        self.harness.update_relation_data(
            db_rel_id,
            "postgres-new",
            {
                "username": "some-username",
                "password": "some-password",
                "endpoints": "some.database.host,some.other.database.host",
            },
        )

        self.harness.update_config({"server.url-template": "some-url-template"})

        self.assertEqual(
            self.harness.model.unit.status.message, "Database not initialised, please run the schema-upgrade action."
        )

        check_schema_version_check_output = "Error: database not initialized"

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action("schema-upgrade")

        self.assertListEqual(
            subprocess_check_output_mock.call_args.args[0],
            ["canonical-livepatch-server.check-schema-version", self.harness.charm._state.db_uri],
        )
        self.assertEqual(ex.exception.message, "Schema upgrade failed.")

    def test_set_basic_users_action__success(self):
        """test `set-basic-users` action."""
        self.start_leader_unit()

        self.snap_mock.set = Mock(return_value=None)

        def mock_restart(service: List[str]):
            self.assertEqual(service, ["livepatch"])
            self.snap_mock.services = {"livepatch": {"active": True}}

        self.snap_mock.restart = Mock(side_effect=mock_restart)

        result = self.harness.run_action(
            "set-basic-users",
            {
                "users": "alice:foo,bob:bar",
            },
        )

        def mock_get(key: str):
            self.assertEqual(key, "lp.auth.basic.users")
            return "alice:00000000,bob:00000000"

        self.snap_mock.get = Mock(side_effect=mock_get)

        result_append = self.harness.run_action(
            "set-basic-users",
            {
                "append": True,
                "users": "charlie:baz",
            },
        )

        self.assertEqual(self.snap_mock.set.call_args_list[0].args[0]["lp.auth.basic.enabled"], True)
        self.assertRegex(self.snap_mock.set.call_args_list[0].args[0]["lp.auth.basic.users"], "^alice:.*,bob:.*$")
        self.assertEqual(
            result.results,
            {"users-set": ["alice", "bob"]},
        )

        self.assertEqual(self.snap_mock.set.call_args_list[1].args[0]["lp.auth.basic.enabled"], True)
        self.assertRegex(
            self.snap_mock.set.call_args_list[1].args[0]["lp.auth.basic.users"], "^alice:.*,bob:.*,charlie:.*$"
        )
        self.assertEqual(
            result_append.results,
            {"users-set": ["charlie"]},
        )

    def test_set_basic_users_action__repeated_user(self):
        """test `set-basic-users` action when an existing user is re-added."""
        self.start_leader_unit()

        self.snap_mock.set = Mock(return_value=None)

        def mock_restart(service: List[str]):
            self.assertEqual(service, ["livepatch"])
            self.snap_mock.services = {"livepatch": {"active": True}}

        self.snap_mock.restart = Mock(side_effect=mock_restart)

        result = self.harness.run_action(
            "set-basic-users",
            {
                "users": "alice:foo,bob:bar",
            },
        )

        self.assertEqual(
            result.results,
            {"users-set": ["alice", "bob"]},
        )

        def mock_get(key: str):
            self.assertEqual(key, "lp.auth.basic.users")
            return "alice:00000000,bob:00000000"

        self.snap_mock.get = Mock(side_effect=mock_get)

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action(
                "set-basic-users",
                {
                    "append": True,
                    "users": "alice:baz",
                },
            )

        self.assertEqual(ex.exception.message, "The user alice already exists.")

    def test_set_basic_users_action__long_password(self):
        """test `set-basic-users` action when password is longer than allowed."""
        self.start_leader_unit()

        self.snap_mock.set = Mock(return_value=None)

        def mock_restart(service: List[str]):
            self.assertEqual(service, ["livepatch"])
            self.snap_mock.services = {"livepatch": {"active": True}}

        self.snap_mock.restart = Mock(side_effect=mock_restart)

        with self.assertRaises(ActionFailed) as ex:
            self.harness.run_action(
                "set-basic-users",
                {
                    "users": "alice:password-with-73-chars-00000000000000000000000000000000000000000000000000",
                },
            )

        self.assertRegex(ex.exception.message, "Password: .* cannot be more than 72 characters\\.")

    def test_set_basic_users_action__invalid_arg(self):
        """test `set-basic-users` action when argument is not valid."""
        self.start_leader_unit()
        with self.subTest("users: none"):
            with self.assertRaises(ActionFailed) as ex:
                self.harness.run_action("set-basic-users", {"users": None})

            self.assertEqual(
                ex.exception.message, "No users provided to be set. Please provide users as: users=user:pass,user:pass"
            )

        with self.subTest("users: empty"):
            with self.assertRaises(ActionFailed) as ex:
                self.harness.run_action("set-basic-users", {"users": ""})

            self.assertEqual(
                ex.exception.message, "No users provided to be set. Please provide users as: users=user:pass,user:pass"
            )

        with self.subTest("users: non-string"):
            with self.assertRaises(ActionFailed) as ex:
                self.harness.run_action("set-basic-users", {"users": ["foo"]})

            self.assertEqual(
                ex.exception.message, "Failed to parse users list. Please provide users as: users=user:pass,user:pass"
            )

    def test_custom_ca(self):
        """test setting a custom CA for the contracts server"""
        self.start_leader_unit()
        with tempfile.NamedTemporaryFile() as tmpfile:
            with patch.object(src.charm, "TRUSTED_CA_FILENAME", tmpfile.name):
                self.harness.update_config({"contracts.ca": "dGVzdA=="})
            self.assertTrue(os.path.exists(tmpfile.name))
            self.assertEqual(tmpfile.read().decode(), "test")
