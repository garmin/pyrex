#! /bin/sh

if [ -z "${PYREX_TEST_STARTUP_SCRIPT+isset}" ]; then
    exit 0
fi

echo "Startup script test"
exit $PYREX_TEST_STARTUP_SCRIPT
