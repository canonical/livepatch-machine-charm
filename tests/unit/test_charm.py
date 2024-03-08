# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing
"""Unit tests module."""
import unittest
from unittest.mock import patch

from ops.testing import Harness

from src.charm import OperatorMachineCharm

APP_NAME = "canonical-livepatch-server"


class TestCharm(unittest.TestCase):
    """Unit tests class."""

    def setUp(self):
        self.harness = Harness(OperatorMachineCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.disable_hooks()
        self.harness.begin()

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
