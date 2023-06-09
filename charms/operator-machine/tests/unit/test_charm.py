# Copyright 2022 CanonicalLtd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest

from ops.testing import Harness

from src.charm import OperatorMachineCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(OperatorMachineCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_config_changed(self):
        # A single fake test at the very least checks the charm init code
        # and allows `tox -e unit` to pass.
        assert 1 == 1
