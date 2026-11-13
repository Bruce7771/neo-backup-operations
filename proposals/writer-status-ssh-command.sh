#!/usr/bin/env bash
# REVIEW ONLY. Separate read-only observation identity; legacy key unchanged.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset BASH_ENV ENV CDPATH
readonly status=/usr/local/libexec/neo-offsite-retention-writer-status
[[ $(id -u) == 0 ]] || exit 1
case ${SSH_ORIGINAL_COMMAND:-} in
  writer-status)
    [[ -f $status && ! -L $status && $(stat -c %u "$status") == 0 ]] || exit 1
    mode=$(stat -c %a "$status"); (( (8#$mode & 0022) == 0 )) || exit 1
    exec /usr/bin/python3 "$status" ;;
  *) echo 'Unsupported literal maintenance command' >&2; exit 2 ;;
esac
