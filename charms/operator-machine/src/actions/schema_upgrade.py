from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from charm import OperatorMachineCharm

from ops.charm import ActionEvent
from ops.model import MaintenanceStatus
from util.schema_tool import run_schema_upgrade

def on_schema_upgrade_action(self: OperatorMachineCharm, event: ActionEvent) -> None:
    event.log("Running schema upgrade action...")
    if self.unit.is_leader():
        run_schema_upgrade(self._state.db_uri)
        upgrade_required, version = self._check_schema_upgrade_ran()

        if upgrade_required:
            failure_reason = "Schema upgrade failed."
            self.unit.status = MaintenanceStatus(failure_reason)
            event.log(failure_reason)
            event.set_results({
                "schema-upgrade-required": upgrade_required,
                "schema-version": version
            })
            event.fail(failure_reason)
        else:
            event.log("Schema upgrade was successful.")
            event.set_results({
                "schema-upgrade-required": upgrade_required,
                "schema-version": version
            })
            # As it was successful, we manually run config-changed to speed up
            # the status changing
            #
            # The event type is fine, we nothing StartEvent has been given
            self._config_changed(event)
