#!/bin/bash
export DIR=$(dirname "$0")
echo "DIR: $DIR"
DIR=${PWD-$DIR}
if [ "${DIR}" = "." ]; then
    DIR=${PWD}
fi
echo "DIR: $DIR"

#echo Calculating values. Logging to /var/log/mh/scripts/WeatherCustom.log
echo Calculating values. Logging to ${DIR}/logs/WeatherCustom.log

python $DIR/weatherCustom.py $DIR/logs $DIR/ET $DIR/wuData $DIR/weatherprograms $1 2>&1 | tee logs/weatherCustom.log
