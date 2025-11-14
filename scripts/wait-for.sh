#!/bin/bash

# wait-for.sh - Service readiness helper script
# Waits for a service to be available before continuing
# Usage: ./wait-for.sh host:port [-s timeout]

set -e

waithost="$1"
shift
cmd="$@"

timeout=15

echoerr() { if [ "$QUIET" != "1" ]; then echo "$@" 1>&2; fi }

wait_for() {
  for i in $(seq $timeout) ; do
    nc -z "$1" "$2" > /dev/null 2>&1
    
    result=$?
    if [ $result -eq 0 ] ; then
      if [ -n "$3" ] ; then
        echoerr "$1:$2 is available after $i seconds"
      fi
      return 0
    fi
    if [ $i -lt $timeout ] ; then
      sleep 1
    fi
  done
  echo "Operation timed out" >&2
  return 1
}

case "$waithost" in
  *:* )
    host=$(printf "%s\n" "$waithost"| cut -d : -f 1)
    port=$(printf "%s\n" "$waithost"| cut -d : -f 2)
    wait_for $host $port
    ;;
  *)
    echoerr "Unknown format: $waithost"
    exit 1
    ;;
esac

if [ -n "$cmd" ] ; then
  exec $cmd
fi
