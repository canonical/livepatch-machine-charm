# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Action to set basic users."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

import bcrypt
from ops.charm import ActionEvent
from ops.model import MaintenanceStatus

if TYPE_CHECKING:
    from charm import OperatorMachineCharm

basic_users_enabled_path = "lp.auth.basic.enabled"
basic_users_config_path = "lp.auth.basic.users"


def on_set_basic_users_action(self: OperatorMachineCharm, event: ActionEvent) -> None:
    """
    Set the basic users for the server.

    This action overrides all existing users currently set
    in livepatch, to add an additional user, see add_basic_users_action
    """
    event.log("Setting basic users.")

    def fail_action(msg):
        self.set_status_and_log(msg, MaintenanceStatus)
        event.log(msg)
        event.fail(msg)

    users: str = event.params.get("users")

    if users is None or len(users) == 0:
        fail_action("No users provided to be set. Please provide users as: users=user:pass,user:pass")
        return

    # Rather than list and check type after the fact with instanceof,
    # its better to just hard-fail here.
    try:
        users_list: List[str] = users.split(",")
    except Exception as e:
        fail_action("Failed to parse users list. Please provide users as: users=user:pass,user:pass")
        event.set_results({"error": e})
        return

    hashed_users: List[str] = []
    set_users: List[str] = []

    for u in users_list:
        username, password = u.split(":")
        if len(password) > 72:
            fail_action(f"Password: {password} cannot be more than 72 characters.")
            return
        pwd = bcrypt.hashpw(str.encode(password), bcrypt.gensalt(rounds=10))
        hashed_users.append(f"{username}:{pwd.decode()}")
        set_users.append(username)

    if event.params.get("append") is True:
        existing_users = self.get_livepatch_snap.get(basic_users_config_path)
        if len(existing_users) == 0:
            fail_action("No users exist to append to, please remove the append argument.")
        for existing_user in existing_users.split(","):
            uname = existing_user.split(":")
            if uname[0] in set_users:
                fail_action(f"The user {uname[0]} already exists.")
                return
        self.get_livepatch_snap.set(
            {
                basic_users_enabled_path: True,
                basic_users_config_path: f"{existing_users},{','.join(hashed_users)}",
            }
        )
        event.log("Appending users to current configuration.")
    else:
        self.get_livepatch_snap.set(
            {
                basic_users_enabled_path: True,
                basic_users_config_path: ",".join(hashed_users),
            }
        )

    self.get_livepatch_snap.restart(["livepatch"])

    # If, for any reason, the snap fails to restart, we at least
    # inform the user that the server is no longer running and
    # enter an error state.
    #
    # TODO: Change from maintenance state to error state when you find it Alex
    if self.livepatch_running is not True:
        fail_action("Livepatch server could not be restarted.")
        return
    event.log("Users set successfully.")
    event.set_results({"users-set": set_users})
