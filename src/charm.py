#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Livepatch machine operator charm."""

import logging
import subprocess  # nosec
from typing import Tuple, Union

import pgsql
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v2.snap import Snap, SnapCache, SnapError, SnapState
from ops.charm import CharmBase, ConfigChangedEvent, StartEvent, UpdateStatusEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from constants.errors import SCHEMA_VERSION_CHECK_ERROR
from constants.snap import SERVER_SNAP_NAME, SERVER_SNAP_REVISION
from constants.statuses import (
    AWAIT_POSTGRES_RELATION,
    CHECKING_DB_VERS,
    INSTALLING,
    LIVEPATCH_NOT_INSTALLED_ERROR,
    SUCCESSFUL_INSTALL,
)
from util.schema_tool import run_schema_version_check

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = {
    "server.url-template": "✘ server.url-template config not set",
}

DATABASE_NAME = "livepatch"
DATABASE_RELATION = "database"
DATABASE_RELATION_LEGACY = "database-legacy"


class OperatorMachineCharm(CharmBase):
    """Livepatch on-premise machine charm."""

    _state: StoredState = StoredState()

    @property
    def get_livepatch_snap(self) -> Snap:
        """Retrieves livepatch snap from the snap cache."""
        return self.snap_cache.get(SERVER_SNAP_NAME)

    @property
    def livepatch_installed(self) -> bool:
        """Reports if the Livepatch snap is installed."""
        return self.get_livepatch_snap.present

    @property
    def livepatch_running(self):
        """Reports if the "livepatch" snap daemon is running."""
        return self.get_livepatch_snap.services["livepatch"]["active"]

    def __init__(self, *args) -> None:
        """Init function."""
        super().__init__(*args)
        self._state.set_default(db_uri=None, db_ro_uris=[])

        # Setup snapcache
        self.snap_cache = SnapCache()

        # Hooks
        self.framework.observe(self.on.install, self._install)
        self.framework.observe(self.on.config_changed, self._config_changed)
        self.framework.observe(self.on.update_status, self._update_status)

        # Reverse-proxy
        self.framework.observe(self.on.website_relation_joined, self._on_website_relation_joined)

        # Database (legacy)
        self.db = pgsql.PostgreSQLClient(self, DATABASE_RELATION_LEGACY)
        self.framework.observe(
            self.db.on.database_relation_joined,
            self._on_legacy_db_relation_joined,
        )
        self.framework.observe(self.db.on.master_changed, self._on_legacy_db_master_changed)
        self.framework.observe(self.db.on.standby_changed, self._on_legacy_db_standby_changed)

        # Database
        self.database = DatabaseRequires(
            self,
            relation_name=DATABASE_RELATION,
            database_name=DATABASE_NAME,
        )
        self.framework.observe(self.database.on.database_created, self._on_database_event)
        self.framework.observe(
            self.database.on.endpoints_changed,
            self._on_database_event,
        )

        # Actions
        self.framework.observe(self.on.enable_action, self.on_enable_action)
        self.framework.observe(self.on.schema_upgrade_action, self.on_schema_upgrade_action)
        self.framework.observe(self.on.set_basic_users_action, self.on_set_basic_users_action)
        self.framework.observe(self.on.restart_action, self.on_restart_action)

        # Grafana agent relation
        server_address: str = self.config["server.server-address"]
        server_split = server_address.split(":")
        if len(server_split) != 2:
            logger.warning("Server address config missing port.")
            logger.warning("Won't enable COS observability.")
        else:
            self._grafana_agent = COSAgentProvider(
                self,
                relation_name="cos-agent",
                metrics_endpoints=[
                    {"path": "/metrics", "port": server_split[1]},
                ],
                metrics_rules_dir="./src/alert_rules/prometheus",
                logs_rules_dir="./src/alert_rules/loki",
                recurse_rules_dirs=True,
                dashboard_dirs=["./src/grafana_dashboards"],
            )

    ###################
    # LIFECYCLE HOOKS #
    ###################
    def _install(self, _):
        """Install livepatch snap."""
        self.set_status_and_log(INSTALLING, WaitingStatus)
        # Make sure it installed
        logger.info("Current install state: %s", self.livepatch_installed)
        if not self.livepatch_installed:
            logger.info("Installing livepatch")
            # Ensure it is latest revision on stable.
            self.get_livepatch_snap.ensure(SnapState.Latest, revision=SERVER_SNAP_REVISION)
            self.get_livepatch_snap.hold()
            self.set_status_and_log(SUCCESSFUL_INSTALL, WaitingStatus)
        else:
            self.set_status_and_log("Livepatch snap already installed...", WaitingStatus)

    def _start(self, event: StartEvent):
        """Start livepatch server ensuring the related postgres has been migrated (via the snaps schema-tool)."""
        if self._check_install_and_relations() and self._database_migrated(event):
            self.set_status_and_log("Starting livepatch daemon...", WaitingStatus)
            self.get_livepatch_snap.start(["livepatch"])
            if self.livepatch_running:
                self.set_status_and_log("Livepatch running!", ActiveStatus)

    def _config_changed(self, event: ConfigChangedEvent):
        """Update snap internal configuration, additionally validating the DB is ready each time."""
        required_settings = REQUIRED_SETTINGS.copy()

        for setting, error_msg in required_settings.items():
            if self.config.get(setting) in (None, ""):
                self.set_status_and_log(error_msg, BlockedStatus)
                logger.warning(error_msg)
                return

        if not self._check_install_and_relations():
            return
        if not self._database_migrated(event):
            return

        configuration = {**self.config}

        # Leader specific configurations
        if self.unit.is_leader():
            configuration["server.is-leader"] = True
        else:
            configuration["server.is-leader"] = False

        configuration["database.connection-string"] = self._state.db_uri

        print("Config of database.connection-string is: ", self._state.db_uri)

        # General configuration override logic
        pg_conn_str_conf = "patch-storage.postgres-connection-string"
        if len(self.config.get(pg_conn_str_conf)) == 0:
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
                "error occurred when attempting to set snap configuration value %s",
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
        """Perform a simple service health check."""
        logging.info("Updating application status...")
        current_status = self.unit.status
        if self._check_install_and_relations():
            if self.livepatch_running:
                self.set_status_and_log("Livepatch running!", ActiveStatus)
            elif current_status == ActiveStatus:
                # If the status has been set elsewhere, don't override that.
                # We don't defer, as the server is not running for an unexpected reason
                self.unit.status = MaintenanceStatus("Livepatch is not running.")
            else:
                logging.warning(
                    "Livepatch is not running but current status is %s with message %s",
                    current_status.name,
                    current_status.message,
                )

    # Legacy database

    def _on_legacy_db_relation_joined(self, event: pgsql.DatabaseRelationJoinedEvent) -> None:
        """
        Handle determining if the database (on legacy database relation) has finished setup.

        Once setup is complete a primary/standby may join/change in consequent events.
        """
        logging.info("(postgresql, legacy database relation) RELATION_JOINED event fired.")

        logging.warning(
            f"`{DATABASE_RELATION_LEGACY}` is a legacy relation; try integrating with `{DATABASE_RELATION}` instead."
        )

        if self.model.unit.is_leader():
            # Handle database configurations / changes here!
            if self._is_database_relation_activated():
                logging.error(f"The `{DATABASE_RELATION}` relation is already integrated.")
                raise RuntimeError(
                    "Integration with both database relations is not allowed; "
                    f"`{DATABASE_RELATION}` is already activated."
                )
            event.database = DATABASE_NAME
        elif event.database != DATABASE_NAME:
            event.defer()

    def _on_legacy_db_master_changed(self, event: pgsql.MasterChangedEvent) -> None:
        """
        Handle primary units of postgres joining/changing (for the legacy database relation).

        The internal snap configuration is updated to reflect this.
        """
        logging.info("(postgresql, legacy database relation) MASTER_CHANGED event fired.")

        if event.database != DATABASE_NAME:
            logging.debug("(legacy database relation) Database setup not complete yet, returning.")
            return

        self.set_status_and_log(
            "(legacy database relation) Updating livepatchd database configuration...",
            WaitingStatus,
        )
        # wokeignore:rule=master
        if event.master is not None:
            # Note (babakks): The split is mainly to drop query parameters that may cause further database
            # connection errors. For example, there's this query parameters, named `fallback_application_name`,
            # which causes the schema upgrade command to return `unrecognized configuration parameter
            # "fallback_application_name" (SQLSTATE 42704)`.
            # wokeignore:rule=master
            self._state.db_uri = event.master.uri.split("?", 1)[0]
            print("setting self._state.db_uri here")
        else:
            print("possible bug in setting self._state.db_uri here to None")
            self._state.db_uri = None

        # if self._check_install_and_relations():
        #     self._check_schema_upgrade_required(event)
        self._config_changed(event)

    def _on_legacy_db_standby_changed(self, event: pgsql.StandbyChangedEvent):
        logging.info("(postgresql, legacy database relation) STANDBY_CHANGED event fired.")
        # NOTE
        # wokeignore:rule=master
        # This should be used for none-master on-prem instances when configuring
        # additional livepatch instances, enabling us to read from standbys
        if event.database != DATABASE_NAME:
            # Leader has not yet set requirements. Wait until next event,
            # or risk connecting to an incorrect database.
            return

        # If empty, no standbys available

        # Note (babakks): The split is mainly to drop query parameters that may cause further database
        # connection errors. For example, there's this query parameters, named `fallback_application_name`,
        # which causes the schema upgrade command to return `unrecognized configuration parameter
        # "fallback_application_name" (SQLSTATE 42704)`.
        self._state.db_ro_uris = [c.uri.split("?", 1)[0] for c in event.standbys]

    # Database

    def _is_legacy_database_relation_activated(self) -> bool:
        return len(self.model.relations[DATABASE_RELATION_LEGACY]) > 0

    def _is_database_relation_activated(self) -> bool:
        return len(self.model.relations[DATABASE_RELATION]) > 0

    def _on_database_event(self, event) -> None:
        """Database event handler."""
        if not self.model.unit.is_leader():
            print("Possible bug from this. We should set self._state.db_uri before returning")
            return

        logging.info("(postgresql) RELATION_JOINED event fired.")

        if self._is_legacy_database_relation_activated():
            logging.error(f"The `{DATABASE_RELATION_LEGACY}` relation is already integrated.")
            raise RuntimeError(
                "Integration with both database relations is not allowed; "
                f"`{DATABASE_RELATION_LEGACY}` is already activated."
            )

        if event.username is None or event.password is None:
            event.defer()
            logging.info(
                "(postgresql) Relation data is not complete (missing `username` or `password` field); "
                "deferring the event."
            )
            return

        # get the first endpoint from a comma separate list
        ep = event.endpoints.split(",", 1)[0]
        # compose the db connection string
        uri = f"postgresql://{event.username}:{event.password}@{ep}/{DATABASE_NAME}"

        logging.info(f"received database uri: {uri}")

        # record the connection string
        self._state.db_uri = uri

        # if self._check_install_and_relations():
        #     self._check_schema_upgrade_required(event)
        self._config_changed(event)

    def _on_website_relation_joined(self, event) -> None:
        server_address: str = self.config.get("server.server-address")
        port = server_address.split(":")[1]
        event.relation.data[self.unit]["port"] = port

    ###########
    # ACTIONS #
    ###########
    from actions.enable import on_enable_action
    from actions.restart import on_restart_action
    from actions.schema_upgrade import on_schema_upgrade_action
    from actions.set_basic_users import on_set_basic_users_action

    ###########
    # UTILITY #
    ###########
    def _install_snap(self) -> None:
        """
        Install the Livepatch Server snap.

        Note:
        This is pulled from the lib as out of the box in the lib, it just
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
            _ = subprocess.check_output(_cmd, universal_newlines=True).splitlines()[0]  # nosec

            if self.get_livepatch_snap.present:
                logging.info("Snap: %s installed!", self.get_livepatch_snap.name)
            else:
                raise SnapError("Could not find livepatch snap, TODO make error better")
        except subprocess.CalledProcessError as e:
            raise SnapError(f"Could not install snap {resource_path}: {e.output}") from e

    def _database_migrated(self, event: Union[StartEvent, ConfigChangedEvent, UpdateStatusEvent]) -> bool:
        """Start (or restart if the flag is given) the livepatch snap."""
        self.set_status_and_log(CHECKING_DB_VERS, WaitingStatus)
        upgrade_required, version = self._check_schema_upgrade_ran()

        if upgrade_required:
            self.set_status_and_log(
                "Database not initialised, please run the schema-upgrade action.",
                BlockedStatus,
            )
            return False

        logging.info("Database has been migrated. Current version: %s", version)
        return True

    def _check_install_and_relations(self) -> bool:
        """If returns false, not all is ok, else all good."""
        if self.livepatch_installed is not True:
            # TODO: We need error status, how?
            self.set_status_and_log(LIVEPATCH_NOT_INSTALLED_ERROR, MaintenanceStatus)
            return False

        db_joined = self._is_database_relation_activated()
        legacy_db_joined = self._is_legacy_database_relation_activated()
        if not db_joined and not legacy_db_joined:
            self.set_status_and_log(AWAIT_POSTGRES_RELATION, BlockedStatus)
            return False

        if self._state.db_uri is None:
            if db_joined:
                self.set_status_and_log("Waiting for postgres...", WaitingStatus)
            else:
                self.set_status_and_log(
                    "Waiting for postgres to select primary node...",
                    WaitingStatus,
                )
            return False

        return True

    def _check_schema_upgrade_ran(self) -> Tuple[bool, str]:
        """Check if a schema upgrade has run, and returns true if an upgrade is needed, false otherwise."""
        if self.unit.is_leader():
            result = run_schema_version_check(master_uri=self._state.db_uri)
            if result.splitlines()[0].find(SCHEMA_VERSION_CHECK_ERROR) != -1:
                return True, result
            return False, result
        # the unit is not a leader, so it shouldn't worry about performing a schema upgrade.
        return False, ""

    def set_status_and_log(self, msg, status) -> None:
        """Log and set unit status simultaneously."""
        logging.info(msg)
        self.unit.status = status(msg)


if __name__ == "__main__":
    main(OperatorMachineCharm)
