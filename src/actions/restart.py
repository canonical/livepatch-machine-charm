# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Restart action."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ops.charm import ActionEvent
from ops.model import MaintenanceStatus

if TYPE_CHECKING:
    from charm import OperatorMachineCharm


def on_restart_action(self: OperatorMachineCharm, event: ActionEvent) -> None:
    """Restart the livepatch server daemon service within the snap."""
    event.log("Attempting to restart livepatch server...")

    def fail_action(msg):
        self.set_status_and_log(msg, MaintenanceStatus)
        event.log(msg)
        event.fail(msg)

    if self.livepatch_installed:
        event.log("Restarting livepatch server...")
        self.get_livepatch_snap.restart(["livepatch"])
        event.log("Restart completed, checking service status...")
        if self.livepatch_running:
            event.log("Service restarted successfully.")
            event.set_results({"restarted": "true"})
        else:
            fail_action("Server failed to restart.")
    else:
        fail_action("Livepatch server failed to restart, as the server snap is not installed.")
