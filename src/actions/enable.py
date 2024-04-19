# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Enable livepatch action."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ops.charm import ActionEvent
from ops.model import MaintenanceStatus

if TYPE_CHECKING:
    from charm import OperatorMachineCharm


def on_enable_action(self: OperatorMachineCharm, event: ActionEvent) -> None:
    """Enable livepatch on-prem via Ubuntu Pro."""
    event.log("Attempting to enable livepatch on-prem...")

    def fail_action(msg):
        """Log failure and set status."""
        self.set_status_and_log(msg, MaintenanceStatus)
        event.log(msg)
        event.fail(msg)

    params = event.params

    token: str = params.get("token")

    if token is None or len(token) == 0:
        fail_action("No token provided.")
        return

    if not self.livepatch_installed:
        fail_action("Livepatch snap is not installed.")
        return

    # When setting the "token" configuration option, the snap handles
    # the retrieval of the resource token for us.
    #
    # When it fails to do so, token is left unset, letting us know it failed.
    self.get_livepatch_snap.set({"token": token})
    retrieved_token = self.get_livepatch_snap.get("token")

    if len(retrieved_token) == 0:
        # TODO: This needs improvement, it could've failed due multiple things (network, bad token,
        # expired token etc.)
        # How will we surface these kinds of errors through snap configuration? Perhaps this needs refactoring.
        fail_action("Failed to enable Ubuntu Pro, is your token correct?")
        return

    event.log("Livepatch on-prem enabled.")
    event.set_results({"enabled": "true"})
