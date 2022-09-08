#!/usr/bin/env bash

# This script merges the py-reqs from mcuboot, zephyr, and nrf.
# Then generates a frozen requirments-ci.txt for tests to run with.

#OPTIONAL
OUT_FILE=$1
if [ -z "$OUT_FILE" ]; then
    OUT_FILE=nrf/scripts/requirements-ext.txt
fi
echo "Writing frozen requirements to: $OUT_FILE"

TOPDIR=$(west topdir)
cd $TOPDIR


rm $OUT_FILE
echo "###########################################################" >> $OUT_FILE
echo "#####           Fixed Python Requirements             #####" >> $OUT_FILE
echo "###########################################################" >> $OUT_FILE

echo "" >> $OUT_FILE



source ~/.local/bin/virtualenvwrapper.sh

rmvirtualenv pip-fixed-venv
mkvirtualenv pip-fixed-venv
workon pip-fixed-venv

pip3 install --isolated \
    -r bootloader/mcuboot/scripts/requirements.txt \
    -r zephyr/scripts/requirements.txt  \
    -r nrf/scripts/requirements.txt
pip3 freeze >> $OUT_FILE

deactivate
rmvirtualenv pip-fixed-venv
