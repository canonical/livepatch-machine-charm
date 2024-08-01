#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Livepatch machine operator charm."""

import logging
import subprocess  # nosec
from base64 import b64decode
from typing import Any, Set, Tuple, Union
from urllib.parse import ParseResult, urlunparse

import pgsql
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v2.snap import Snap, SnapCache, SnapError, SnapState
from ops.charm import (
    CharmBase,
    ConfigChangedEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    Relation,
    RelationDataContent,
    WaitingStatus,
)

from constants.errors import SCHEMA_VERSION_CHECK_ERROR
from constants.snap import SERVER_SNAP_NAME, SERVER_SNAP_REVISION
from constants.statuses import (
    AWAIT_POSTGRES_RELATION,
    CHECKING_DB_VERS,
    INSTALLING,
    LIVEPATCH_NOT_INSTALLED_ERROR,
    SUCCESSFUL_INSTALL,
)
from state import State
from util.schema_tool import run_schema_version_check

logger = logging.getLogger(__name__)

REQUIRED_SETTINGS = {
    "server.url-template": "✘ server.url-template config not set",
}

DATABASE_NAME = "livepatch"
DATABASE_RELATION = "database"
DATABASE_RELATION_LEGACY = "database-legacy"
TRUSTED_CA_FILENAME = "/usr/local/share/ca-certificates/trusted-contracts.ca.crt"


class OperatorMachineCharm(CharmBase):
    """Livepatch on-premise machine charm."""

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
        self._state = State(self.app, lambda: self.model.get_relation("livepatch"))
        self.framework.observe(self.on.livepatch_relation_changed, self._on_livepatch_relation_changed)

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

        # Air-gapped pro/contracts
        self.framework.observe(
            self.on.pro_airgapped_server_relation_changed, self._on_pro_airgapped_server_relation_changed
        )
        self.framework.observe(
            self.on.pro_airgapped_server_relation_departed, self._on_pro_airgapped_server_relation_departed
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

    def _on_livepatch_relation_changed(self, event) -> None:
        """Handle peer `relation-changed` event."""
        self._config_changed(event)

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

    def _check_required_config_assigned(self) -> bool:
        """
        Check required configuration parameters are assigned.

        This will set the status as blocked if any of the required parameters
        were not set.
        """
        required_settings = REQUIRED_SETTINGS.copy()
        for setting, error_msg in required_settings.items():
            if self.config.get(setting) in (None, ""):
                self.set_status_and_log(error_msg, BlockedStatus)
                logger.warning(error_msg)
                return False
        return True

    def _config_changed(self, event: Union[ConfigChangedEvent, None]):
        """Update snap internal configuration, additionally validating the DB is ready each time."""
        can_continue = (
            self._check_required_config_assigned() and self._check_install_and_relations() and self._database_migrated()
        )
        if not can_continue:
            return

        self._update_trusted_ca_certs()

        configuration = {**self.config}

        # Leader specific configurations
        configuration["server.is-leader"] = self.unit.is_leader()
        configuration["database.connection-string"] = self._state.db_uri

        # General configuration override logic
        pg_conn_str_conf = "patch-storage.postgres-connection-string"
        if len(self.config.get(pg_conn_str_conf)) == 0:
            configuration["patch-storage.postgres-connection-string"] = self._state.db_uri

        if self.config.get("patch-sync.enabled") is True:
            # TODO: Test this alex
            configuration["patch-sync.id"] = self.model.uuid

        if self._state.pro_airgapped_address:
            configuration["contracts.enabled"] = True
            configuration["contracts.url"] = self._state.pro_airgapped_address
            configuration.pop("contracts.user", None)
            configuration.pop("contracts.password", None)

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

        try:
            self.get_livepatch_snap.restart(["livepatch"])
        except SnapError as e:
            logging.error("error occurred when attempting to restart snap: %s", e)
            self.set_status_and_log("Livepatch failed to restart.", MaintenanceStatus)
            if event is not None:
                event.defer()
            return

        if self.unit.status.message == AWAIT_POSTGRES_RELATION:
            if event is not None:
                event.defer()
            return

        if self.livepatch_running is not True:
            self.set_status_and_log("Livepatch failed to restart.", MaintenanceStatus)
            if event is not None:
                event.defer()
            return

        self._update_status(event)

    def _update_status(self, _: Any) -> None:
        """Perform a simple service health check."""
        logging.info("Updating application status...")
        current_status = self.unit.status
        if self._check_install_and_relations():
            if self.livepatch_running:
                self.set_status_and_log("Livepatch running!", ActiveStatus)
            elif isinstance(current_status, ActiveStatus):
                # If the status has been set elsewhere, don't override that.
                # We don't defer, as the server is not running for an unexpected reason
                self.unit.status = MaintenanceStatus("Livepatch is not running.")
            else:
                logging.warning(
                    "Livepatch is not running but current status is %s with message %s",
                    current_status.name,
                    current_status.message,
                )

    def _update_trusted_ca_certs(self):
        """Update trusted CA certificates with the cert from configuration."""
        if not self.config.get("contracts.ca"):
            logging.debug("ca config not set")
            return

        cert = b64decode(self.config.get("contracts.ca")).decode("utf8")
        cert_hash = hash(cert)
        if self._state.contract_cert_hash and cert_hash == self._state.contract_cert_hash:
            return

        with open(TRUSTED_CA_FILENAME, "wt") as f:
            f.write(cert)
        self._state.contract_cert_hash = cert_hash
        result = subprocess.check_output(["update-ca-certificates", "--fresh"], stderr=subprocess.STDOUT)  # nosec
        logger.info("output update-ca-certificates: %s", result)
        return

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

        if not self.model.unit.is_leader():
            return

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
        else:
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

    def _on_website_relation_joined(self, event: RelationEvent) -> None:
        server_address: str = self.config.get("server.server-address")
        port = server_address.split(":")[1]
        event.relation.data[self.unit]["port"] = port

    def _on_pro_airgapped_server_relation_changed(self, event: RelationChangedEvent):
        """Handle pro-airgapped-server relation-changed event."""
        if not self.model.unit.is_leader():
            return
        if not event.unit:
            return
        data = event.relation.data.get(event.unit, None)
        if not data:
            return

        if not self._state.is_ready():
            event.defer()
            return

        available_addresses = self._get_available_pro_airgapped_server_addresses(event.relation)
        if len(available_addresses) == 0:
            logger.error("expected at least one pro-airgapped-server address, but so far none provided by the relation")
            return

        logger.debug("found %d available addresses for pro-airgapped-server", len(available_addresses))

        # Only change the address already stored in the state, if the old one is
        # None or no longer available. This is to avoid unnecessary service restarts.
        current_address = self._state.pro_airgapped_address
        if not current_address or current_address not in available_addresses:
            address = available_addresses.pop()
            logger.info("changing pro-airgapped-server address to %s", address)
            self._state.pro_airgapped_address = address
            self._config_changed(event)

    def _on_pro_airgapped_server_relation_departed(self, event: RelationDepartedEvent):
        """Handle pro-airgapped-server relation-departed event."""
        if not self.model.unit.is_leader():
            return
        if not self._state.is_ready():
            event.defer()
            return

        if len(event.relation.units) == 0:
            # There is no pro-airgapped-server unit related to this charm, so we should opt out
            # of using airgapped contracts.
            logger.warning("falling back to default behavior since all pro-airgapped-server units quit the relation")
            del self._state.pro_airgapped_address
            self._config_changed(event)
            return

        # There might be other units of the pro-airgapped-server in the relation, so we should
        # use the URL from them. Note that this is a very rare scenario, because the airgapped
        # contracts service is usually deployed with one unit. But we nevertheless we have to
        # handle this scenario.
        available_addresses = self._get_available_pro_airgapped_server_addresses(event.relation)
        if len(available_addresses) > 0:
            current_address = self._state.pro_airgapped_address
            if current_address not in available_addresses:
                address = available_addresses.pop()
                logger.info("changing pro-airgapped-server address to %s", address)
                self._state.pro_airgapped_address = address
                self._config_changed(event)
            return

        # We couldn't find a valid address to the pro-airgapped-server, so we have to fallback to default.
        logger.warning("falling back to default behavior since no valid address to pro-airgapped-server is available")
        del self._state.pro_airgapped_address
        self._config_changed(event)

    def _get_available_pro_airgapped_server_addresses(self, relation: Relation) -> Set[str]:
        """Return available pro-airgapped-server addresses taken from related unit databags."""
        available_addresses: Set[str] = set()
        for u in relation.units:
            data = relation.data.get(u, None)
            if not data:
                continue
            address = self._extract_pro_airgapped_server_address(data)
            if not address:
                continue
            available_addresses.add(address)
        return available_addresses

    def _extract_pro_airgapped_server_address(self, data: RelationDataContent) -> Union[str, None]:
        """
        Extract pro-airgapped-server address from given unit databag.

        The method returns None, if data structure is not valid.
        """
        hostname = data.get("hostname")
        if not hostname:
            logger.error("empty 'hostname' value in pro-airgapped relation data")
            return None

        scheme = data.get("scheme") or "http"
        port = data.get("port")
        netloc = hostname + (f":{port}" if port else "")
        return urlunparse(ParseResult(scheme, netloc, "", "", "", ""))

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

    def _database_migrated(self) -> bool:
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
