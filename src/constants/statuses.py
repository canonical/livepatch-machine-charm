# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Status Constants."""

LIVEPATCH_NOT_INSTALLED_ERROR = "Livepatch snap not installed, re-install the charm or run the install hook again."
CHECKING_DB_VERS = "Checking database schema version..."
INSTALLING = "Installing livepatch server..."
SUCCESSFUL_INSTALL = "Snap installed! Waiting on postgres relation..."
AWAIT_POSTGRES_RELATION = "Waiting for postgres relation to be established."
