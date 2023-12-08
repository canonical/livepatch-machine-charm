#!/bin/bash
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

# This script updates the Livepatch Server Snap revision constant used by the charm
# and creates a new branch of the form "server-snap-revision-$1".
# It accepts a single argument - the new snap revision.

update_revision() {
  # Set the file name
  file="./src/constants/snap.py"

  # Check if the file exists
  if [ ! -f "$file" ]; then
    echo "Error: File $file not found."
    return 1
  fi

  # Update the integer in the specified line
  sed -i "s/SERVER_SNAP_REVISION = [0-9]*/SERVER_SNAP_REVISION = $1/" "$file"

  echo "Updated SERVER_SNAP_REVISION to $1 in $file"
}

if [ -z "$1" ]; then
  echo "Usage: update_revision <new_revision>"
  exit 1
fi
update_revision "$1"
git checkout -b "server-snap-revision-$1"
git add .
git commit -m "Updated server snap revision to v$1"
git push
