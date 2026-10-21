#!/bin/sh
# Blender headless with its own profile in out/blender, so MPFB and its assets stay out of the user's.
set -e
here=$(cd "$(dirname "$0")" && pwd)
profile="$here/out/blender"
mkdir -p "$profile"
export BLENDER_USER_RESOURCES="$profile"
export BLENDER_USER_CONFIG="$profile/config"
export BLENDER_USER_SCRIPTS="$profile/scripts"
export BLENDER_USER_EXTENSIONS="$profile/extensions"
export BLENDER_USER_DATAFILES="$profile/datafiles"
exec "${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}" "$@"
