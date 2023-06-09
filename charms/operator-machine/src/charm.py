#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""
Livepatch machine operator charm
"""

import logging
import subprocess
from typing import Tuple, Union

import pgsql
from charms.operator_libs_linux.v1.snap import Snap, SnapCache, SnapError, SnapState
from ops.charm import CharmBase, ConfigChangedEvent, StartEvent, UpdateStatusEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from constants.errors import SCHEMA_VERSION_CHECK_ERROR
from constants.snap import SERVER_SNAP_NAME
from constants.statuses import (
    AWAIT_POSTGRES_RELATION,
    CHECKING_DB_VERS,
    INSTALLING,
    LIVEPATCH_NOT_INSTALLED_ERROR,
    SUCCESSFUL_INSTALL,
)
from util.schema_tool import run_schema_version_check

logger = logging.getLogger(__name__)


class OperatorMachineCharm(CharmBase):
    """
    Livepatch on-premise machine charm
    """

    _state: StoredState = StoredState()

    @property
    def get_livepatch_snap(self) -> Snap:
        """Retrieves livepatch snap from the snap cache"""
        return self.snap_cache.get(SERVER_SNAP_NAME)

    @property
    def livepatch_installed(self) -> bool:
        """Reports if the Livepatch snap is installed."""
        return self.get_livepatch_snap.present

    @property
    def livepatch_running(self):
        """Reports if the "livepatch" snap daemon is running."""
        return self.get_livepatch_snap.services["livepatch"]["active"]

    def __init__(self, *args):
        super().__init__(*args)
        self._state.set_default(db_conn_str=None, db_uri=None, dbn_ro_uris=[])

        # Setup snapcache
        self.snap_cache = SnapCache()

        # Hooks
        self.framework.observe(self.on.install, self._install)
        # self.framework.observe(self.on.start, self._start)
        self.framework.observe(self.on.config_changed, self._config_changed)
        self.framework.observe(self.on.update_status, self._update_status)

        # Database
        self.db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(self.db.on.database_relation_joined, self._on_database_relation_joined)
        self.framework.observe(self.db.on.master_changed, self._on_master_changed)
        self.framework.observe(self.db.on.standby_changed, self._on_standby_changed)

        # Actions
        self.framework.observe(self.on.schema_upgrade_action, self.on_schema_upgrade_action)
        self.framework.observe(self.on.set_basic_users_action, self.on_set_basic_users_action)
        self.framework.observe(self.on.restart_action, self.on_restart_action)

    ###################
    # LIFECYCLE HOOKS #
    ###################
    def _install(self, _):
        """
        Install livepatch snap
        """
        self.set_status_and_log(INSTALLING, WaitingStatus)
        # Make sure it installed
        logger.info("Current install state: %s", self.livepatch_installed)
        if not self.livepatch_installed:
            logger.info("Installing livepatch")
            # Ensure it is latest revision on edge.
            self.get_livepatch_snap.ensure(SnapState.Latest, channel="edge")
            self.set_status_and_log(SUCCESSFUL_INSTALL, WaitingStatus)
        else:
            self.set_status_and_log("Livepatch snap already installed...", WaitingStatus)

    def _start(self, event: StartEvent):
        """
        Starts livepatch server ensuring the related postgres
        has been migrated (via the snaps schema-tool)
        """
        if self._check_install_and_relations() and self._check_schema_upgrade_required(event):
            self.set_status_and_log("Starting livepatch daemon...", WaitingStatus)
            self.get_livepatch_snap.start(["livepatch"])
            if self.livepatch_running:
                self.set_status_and_log("Livepatch running!", ActiveStatus)

    def _config_changed(self, event: ConfigChangedEvent):
        """
        Updates snap internal configuration, additionally
        validating the DB is ready each time.
        """
        if self._check_install_and_relations() and self._check_schema_upgrade_required(event):
            configuration = {**self.config}
            # Leader specific configurations
            if self.unit.is_leader():
                configuration["server.is-leader"] = True
                configuration["database.connection-string"] = self._state.db_uri
            else:
                configuration["server.is-leader"] = False
                # TODO: Handle RO URIs
                configuration["database.connection-string"] = self._state.db_uri
            # General configuration override logic
            if len(self.config.get("patch-storage.postgres-connection-string")) == 0:
                configuration["patch-storage.postgres-connection-string"] = self._state.db_uri
            if self.config.get("patch-sync.enabled") == "True":
                # TODO: Test this alex
                configuration["patch-sync.id"] = self.model.uuid

            try:
                prefixed_configuration = {f"lp.{key}": val for key, val in configuration.items()}
                self.get_livepatch_snap.set(prefixed_configuration)
            except SnapError as e:
                # This *shouldn"t* fire, but would rather be safe!
                logging.error(
                    "error occured when attempting to set snap configuration value %s",
                    e,
                )

            self.set_status_and_log("Restarting livepatch daemon...", WaitingStatus)
            self.get_livepatch_snap.restart(["livepatch"])

            if self.unit.status.message == AWAIT_POSTGRES_RELATION:
                event.defer()
                return

            if self.livepatch_running is not True:
                self.set_status_and_log("Livepatch failed to restart.", MaintenanceStatus)
                event.defer()
            else:
                self._update_status(event)

    def _update_status(self, event: UpdateStatusEvent) -> None:
        """
        Performs a simple service health check
        TODO: Hit debug status and check active checks to give better
        update statuses
        """
        logging.info("Updating application status...")
        if self._check_install_and_relations():
            if self.livepatch_running:
                self.set_status_and_log("Livepatch running!", ActiveStatus)
            else:
                # We don't defer, as the server is not running for an unexpected reason
                self.unit.status = MaintenanceStatus("Livepatch is not running.")

    def _on_database_relation_joined(self, event: pgsql.DatabaseRelationJoinedEvent) -> None:
        """
        Handles determining if the database has finished setup, once setup is complete
        a master/standby may join / change in consequent events.
        """
        logging.info("(postgresql) RELATION_JOINED event fired.")

        if self.model.unit.is_leader():
            # Handle database configurations / changes here!
            event.database = "livepatch"
        elif event.database != "livepatch":
            event.defer()

    def _on_master_changed(self, event: pgsql.MasterChangedEvent) -> None:
        """
        Handles master units of postgres joining / changing.
        The internal snap configuration is updated to reflect this.
        """
        logging.info("(postgresql) MASTER_CHANGED event fired.")

        if event.database != "livepatch":
            logging.debug("Database setup not complete yet, returning.")
            return

        self.set_status_and_log("Updating livepatchd database configuration...", WaitingStatus)

        self._state.db_conn_str = None if event.master is None else event.master.conn_str
        self._state.db_uri = None if event.master is None else event.master.uri
        if self._check_install_and_relations():
            self._check_schema_upgrade_required(event)

    def _on_standby_changed(self, event: pgsql.StandbyChangedEvent):
        logging.info("(postgresql) STANDBY_CHANGED event fired.")
        # NOTE NOTE NOTE
        # This should be used for none-master on-prem instances when configuring
        # additional livepatch instances, enabling us to read from standbys
        if event.database != "livepatch":
            # Leader has not yet set requirements. Wait until next event,
            # or risk connecting to an incorrect database.
            return

        # If empty, no standbys available
        self._state.db_ro_uris = [c.uri for c in event.standbys]

    ###########
    # ACTIONS #
    ###########
    from actions.restart import on_restart_action
    from actions.schema_upgrade import on_schema_upgrade_action
    from actions.set_basic_users import on_set_basic_users_action

    ###########
    # UTILITY #
    ###########
    def _install_snap(self) -> None:
        """
        Installs the Livepatch Server snap.

        Note:
        This is pulled from the lib as out of the box inthe lib, it just
        doesn't work...
        """
        resource_path = self.model.resources.fetch("livepatch-snap")
        _cmd = [
            "snap",
            "install",
            resource_path,
            "--classic",
            "--dangerous",
        ]
        try:
            logging.info("Attempting to install livepatch snap...")
            subprocess.check_output(_cmd, universal_newlines=True).splitlines()[0]

            if self.get_livepatch_snap.present:
                logging.info("Snap: %s installed!", self.get_livepatch_snap.name)
            else:
                raise SnapError("Could not find livepatch snap, TODO make error better")
        except subprocess.CalledProcessError as e:
            raise SnapError("Could not install snap {}: {}".format(resource_path, e.output))

    def _check_schema_upgrade_required(self, event: Union[StartEvent, ConfigChangedEvent, UpdateStatusEvent]) -> bool:
        """
        Starts (or restarts if the flag is given) the livepatch snap.
        """
        self.set_status_and_log(CHECKING_DB_VERS, WaitingStatus)
        upgrade_required, version = self._check_schema_upgrade_ran()

        if upgrade_required:
            self.set_status_and_log(
                "Database not initialised, please run the schema-upgrade action.",
                BlockedStatus,
            )
            event.defer()
            return False
        else:
            logging.info("Database has been migrated. Current version: %s", version)
            return True

    def _check_install_and_relations(self) -> bool:
        """
        If returns false, not all is ok, else all good.
        """
        if self.livepatch_installed is not True:
            # TODO: We need error status, how?
            self.set_status_and_log(LIVEPATCH_NOT_INSTALLED_ERROR, MaintenanceStatus)
            return False

        if self.model.get_relation(self.db.relation_name) is None:
            self.set_status_and_log(AWAIT_POSTGRES_RELATION, BlockedStatus)
            return False

        if self._state.db_uri is None:
            self.set_status_and_log("Waiting for postgres to select master node...", WaitingStatus)
            return False

        return True

    def _check_schema_upgrade_ran(self) -> Tuple[bool, str]:
        """
        Checks if a schema upgrade has run, and returns true if an upgrade is needed, false otherwise.
        """
        if self.unit.is_leader():
            result = run_schema_version_check(master_uri=self._state.db_uri)
            if result.splitlines()[0].find(SCHEMA_VERSION_CHECK_ERROR) != -1:
                return True, result
            return False, result

    def set_status_and_log(self, msg, status) -> None:
        """
        A simple wrapper to log and set unit status simultaneously.
        """
        logging.info(msg)
        self.unit.status = status(msg)


if __name__ == "__main__":
    main(OperatorMachineCharm)
