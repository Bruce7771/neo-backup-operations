#!/usr/bin/env bash
# PREPARED ONLY. Root-owned forced-command entry; not installed or authorized_keys.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset BASH_ENV ENV CDPATH
readonly helper=/usr/local/libexec/neo-offsite-retention-fence
[[ $(id -u) == 0 && -x $helper && ! -L $helper ]] || exit 1
[[ $(stat -c %u "$helper") == 0 ]] || exit 1
mode=$(stat -c %a "$helper")
(( (8#$mode & 0022) == 0 )) || exit 1
# Literal command allowlist: never evaluate SSH_ORIGINAL_COMMAND as shell text.
case ${SSH_ORIGINAL_COMMAND:-} in
    status) exec "$helper" status ;;
    'acquire 300') exec "$helper" acquire 300 ;;
    release) exec "$helper" release ;;
    *) echo 'Only status, acquire 300, release are permitted' >&2; exit 2 ;;
esac
