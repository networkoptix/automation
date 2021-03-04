#!/bin/bash

declare -r REFNAME="${1}"

echo "${REFNAME}" | grep '^[a-zA-Z0-9_/.-]\+$' >/dev/null
if [[ $? -ne 0 ]]
then
    cat <<ERROR_MESSAGE
GL-HOOK-ERR: Nx Update hook: Branch name policy violated.
${REFNAME#refs/heads/} does not match regular expression ^[a-zA-Z0-9_/.-]\+\$

See also https://networkoptix.atlassian.net/wiki/spaces/SD/pages/491601/Repository+Rules+Branches+Tags+Commits#Branches-naming
ERROR_MESSAGE
    exit 1
fi
