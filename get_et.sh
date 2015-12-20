#!/bin/bash
DIR=$(dirname "$0")

echo Calculating values. Logging to /var/log/mh/scripts/WeatherCustom.log

python $DIR/weatherCustom.py $DIR/logs $DIR/ET $DIR/wuData $DIR/weatherprograms >> /var/log/mh/scripts/weatherCustom.log
