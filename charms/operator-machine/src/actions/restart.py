from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from charm import OperatorMachineCharm

from ops.charm import ActionEvent
from ops.model import MaintenanceStatus


def on_restart_action(self: OperatorMachineCharm, event: ActionEvent) -> None:
    """
    Restarts the livepatch server daemon service within the snap.
    """
    event.log("Attempting to restart livepatch server...")

    def fail_action(msg):
        self.set_status_and_log(msg, MaintenanceStatus),
        event.log(msg),
        event.fail(msg),

    if self.livepatch_installed and self.livepatch_running:
        event.log("Restarting livepatch server...")
        self.get_livepatch_snap.restart(["livepatch"])
        event.log("Restart completed, checking service status...")
        if self.livepatch_running:
            event.log("Service restarted successfully.")
            self._check_server_is_safe_to_start(event)
        else:
            fail_action("Server failed to restart.")
    else:
        fail_action("Livepatch server failed to restart, as the server is not running and/or installed.")
