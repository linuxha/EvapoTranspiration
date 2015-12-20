#!/usr/bin/python
# -*- coding: utf-8 -*-

import cgi
import math
import os
import datetime
import time
import sys
import json
import traceback

debug = os.getenv('NJCDEBUG', 0)                          # Turn on debug messages

from datetime import date, datetime, timedelta

# sys.path.append('./sitelibs')
sys.path.append(os.path.join(os.path.dirname(__file__), 'sitelibs'))

import pytz
import requests
from eto import *

#-[ Purpose ]------------------------------------------------------------------
"""
https://opensprinkler.com/forums/topic/penmen-monteith-eto-method-python-script-for-possible-use-as-weather-script/
http://www.fao.org/docrep/x0490e/x0490e08.htm (Chapter 4 - Determination of ETo)
 (ET = evapotranspiration)

I have included a quickly put together file using either the P-M ETo
method or if enough data is not available the Hargreaves ETo method.

The theory is that a user would create a program using the number of
seconds required to distribute 1mm of water in the coverage area.
This would be saved as a program called 1mm.  After doing this the
user then inputs their WU api key just as they would for the Zimmerman
method.  The script included would then read the current need or
excess water from the logs stored on the uSD card and create a dynamic
program with runtimes utilizing the best averages for decorative
grasses/drip systems, or a standard lawn grass used in the majority of
the world.

The script accounts for wind, freezing conditions, and current/recent
rainfall when considering start and run times.  It will avoid watering
during midday, unless early morning winds prevent earlier start times.
The starts are serialized so no odd overlaps should occur.  Mornings
are preferred to evenings to allow for the best use of water and
absorption without causing mold and fungus growth by leaving grass wet
overnight.  The script is commented quite heavily, so that anyone my
edit or use it to their liking.  Please be mindful that other authors
work was used or modified when the code seemed generalized enough that
I shouldn’t be stepping on toes.  Please do not pester the original
author if something doesn’t work for you, as they will probably have
enough on their own plate with their own original works.

If someone smarter than myself can find a way to hack this into the
current Firmware for OS I would be extremely grateful as I’m sure
quite a few others would be.  This script should comply with most
watering restrictions in the US, however, I must say use at your own
risk, I simply don’t have the time to puruse the near 600 pages of
legal craziness for California alone.

Everything is done based off your latitude and longitude, however, the
script can find the info when provided with a city/state or country, a
US Zip Code, or a PWS ID.

================================================================================
Directory structure
.
./weatherCustom.py              # (ro) main Python code
./sitelibs                      #      Local python libraries (add to sys.path)
./weatherprograms               #      Not programs in the OS sense
./weatherprograms/1mm           # (ro) contains the # of sec required to distribute 1mm of water in the coverage area (1 for each station)
                                #      {"mmTime":[15,16,20,10,30,30],"crop":[1,1,1,1,0,0]} // 6 stations (I'm using 4 so my data will differ slightly)
                                # Crop is a 0 or 1 for grass or shrubs respecticvely. If a zone is primarily flowers 1 should be used for that zone.
                                # Primarily grass or low growing plants (less than about 4 inches high) should use 0. This will denote which ETo value
                                # to use.
./weatherprograms/run           # (rw) runtime 
                                #      [[-1, -1, -1, -1], [0, 0, 0, 0, 0, 0]] // ???
                                # The -1 is the start times in minutes from midnight if a start time is needed. -1 means disabled
./weatherprograms/minmax        # (ro) 
                                #      [5,15]
./ET                            # running totals for day to day [ grasses, shrubs ] in mm
./ET/16775                      # (rw) final daily water balance for Epoch day 16775 (Yesterday)
./ET/16776                      # (rw) final daily water balance for Epoch day 16776 (Today)
./logs                          #
./logs/16776                    # (rw) Epoch day 16776 log of [pid,x,runTime[x]] ... x is station, runTime is in seconds
./wuData                        #
./wuData/16776                  # (w)  Epoch day 16776 csv

wuData/16776 csv format (tabbed):
  observation_epoch
  weather
  temp_f
  temp_c
  relative_humidity
  wind_degrees
  wind_mph
  wind_kph
  precip_1hr_in
  precip_1hr_metric
  precip_today_string
  precip_today_in
  precip_today_metric
  noWater
"""

try:
    logsPath = sys.argv[1]
except:
    logsPath = 'logs'
try:
    ETPath = sys.argv[2]
except:
    ETPath = 'ET'
try:
    wuDataPath = sys.argv[3]
except:
    wuDataPath = 'wuData'
#
try:
    WPPath = sys.argv[4]
except:
    WPPath = 'weatherprograms'
# My debugging code
try:
    today = int(sys.argv[5])
except:
    today = ''
#
if debug != 0: print >>sys.stderr, "E: Today = %s" % (today)

###########################################################################################################
##                                   Credits                                                             ##
###########################################################################################################
## portions of code provided by Zimmerman method used by OpenSprinkler                                   ##
## portions of code provided/edited by Ray and Samer of OpenSprinkler                                    ##
## Compilation of this file and original code provided by Shawn Harte 2014 no copyright reserved         ##
## If you find use of your code unreasonable please contact shawn@veuphoria.com for removal or rewrite   ##
## please contact original authors with respect to their works, I can support only this effort           ##
## Code was used with utmost respect to the original authors, your efforts have prevented the            ##
## re-invention of the wheel, Thanks for your dedication to the OpenSprinkler project                    ##
###########################################################################################################

# define safe functions for variable conversion, preventing errors with NaN and Null as string values
# 's'=value to convert 'dv'=value to default to on error make sure this is a legal float or integer value

def safe_float(s, dv=0.0):
    try:
        return float(s)
    except:
        return dv
    #
#
def safe_int(s, dv=0):
    try:
        return int(float(s))
    except:
        return dv
    #
#
def isInt(s):
    try:
        _v = int(s)
    except:
        return 0
    #
    return 1
#

def isFloat(s):
    try:
        _f = float(s)
    except:
        return 0
    #
    return 1
#

# def main():

print 'Content-Type: text/html'
print ''

# get variables passed from os through the main.js

form = cgi.FieldStorage()
loc  = form.getfirst('loc', '')
key  = form.getfirst('key', '')
of   = form.getfirst('format', '')
pw   = form.getfirst('pw', '')
pid  = safe_int(form.getfirst('pid', ''))  # program id for weather program that uses this adjustment we will need to read the log for it
rainfallsatpoint = form.getfirst('rsp', '25')  # maximum rain to be used for ET calculations

######## Test Data Section #############
# Pull some of the data from the env instead of hard coding it
myurl = os.getenv('NJCURL',   'http://mozart.uucp/data/') # this way I'm not downloading from WU during test
loc   = os.getenv('NJCLOC',   '')                         # where's waldo? ;-)
key   = os.getenv('WUKEY',    '')
#########Dummy Data Section ############
if loc == '':
    loc  = '40.00,-74.00'
#
if key == '':
    key  = 'bad_key_DontUse'
#
if of  == '':
    of   = 'json'
#
if pid == 0:
    pid  = 2
#

# This will create an effective maximum for rain
# ...after this rain will not cause negative ET calculations (huh?)
rainfallsatpoint = 25

########################################

def getTZoneOffset(tz):
    if tz:
        try:
            tnow = pytz.utc.localize(datetime.utcnow())
            tdelta = tnow.astimezone(pytz.timezone(tz)).utcoffset()
            return {'t': tdelta.days * 96 + tdelta.seconds / 900 + 48,
                    'gmt': (86400 * tdelta.days + tdelta.seconds) \
                    / 3600}
        except:
            return {'t': None, 'gmt': None}
        #
    #
#

#########################################
## We need your latitude and longitude ##
## Let's try to get it with no api call##
#########################################

# Hey we were given what we needed let's work with it

sp = loc.split(',', 1)
if len(sp) == 1:
    sp = loc.split(' ', 1)
#
if len(sp) == 2 and isFloat(sp[0]) and isFloat(sp[1]):
    lat = sp[0].strip()
    lon = sp[1].strip()
else:
    lat = None
    lon = None
#

# We got a 5+4 zip code, we only need the 5

sp = loc.split('-', 1)
if len(sp) == 2 and isInt(sp[0]) and len(sp[0]) == 5 and isInt(sp[1]) and len(sp[1]) == 4:
    loc = sp[0]
#

# We got a pws id, we don't need to tell wunderground,
# they know how to deal with the id numbers

if loc.lower().startswith('pws:'):
    loc = loc.lower().replace('pws:', '')
#

# Okay we finally have our loc ready to look up

noData = 0
if lat == None and lon == None:
    try:
        req = requests.get('http://autocomplete.wunderground.com/aq?format=json&query=' + loc)
        data = req.json()
        if data['RESULTS']:
            chk = data['RESULTS'][0]['ll']  # # ll has lat and lon in one spot no matter how we search
            if chk:
                ll = chk.split(' ', 1)
                if len(ll) == 2 and isFloat(ll[0]) and isFloat(ll[1]):
                    lat = ll[0]
                    lon = ll[1]
                #
            #
            chk = data['RESULTS'][0]['tz']
            if chk:
                tzone = chk
            else:
                chk = data['RESULTS'][0]['tz_long']
                if chk:
                    tzone = chk
                #
            #
            chk = data['RESULTS'][0]['name']  # # this is great for showing a pretty name for the location
            if chk:
                ploc = chk
            #
            chk = data['RESULTS'][0]['type']
            if chk:
                whttyp = chk
            #
        #
    except:
        noData = 1
        lat    = None
        lon    = None
        tzone  = None
        ploc   = None
        whttyp = None
    #
else:
    tzone = None
#

# Okay if all went well we got what we needed and snuck in a few more items we'll store those somewhere

if lat and lon:
    try:
        print 'For the %s named: %s the lat, lon is: %s, %s, and the timezone is %s' \
            % (whttyp, ploc, lat, lon, tzone)
    except:
        print 'Resolved your lat:%s, lon:%s, they will be stored' \
            % (lat, lon)
    loc = '' + lat + ',' + lon
else:
    if noData:
        print "Oops couldn't reach Weather Underground check connection"
    else:
        print "Oops %s can't resolved try another location" % loc
#

# Mapping of conditions to a level of shading.
# Since these are for sprinklers any hint of snow will be considered total cover (10)
# Don't worry about wet conditions like fog these are accounted for below we are only concerned with how much sunlight is blocked at ground level

conditions = {
    'Clear': 0,
    'Partial Fog': 2,
    'Patches of Fog': 2,
    'Haze': 2,
    'Shallow Fog': 3,
    'Scattered Clouds': 4,
    'Unknown': 5,
    'Fog': 5,
    'Partly Cloudy': 5,
    'Mostly Cloudy': 8,
    'Mist': 10,
    'Funnel Cloud': 10,
    'Heavy Blowing Snow': 10,
    'Heavy Fog': 10,
    'Heavy Low Drifting Snow': 10,
    'Heavy Rain': 10,
    'Heavy Rain Showers': 10,
    'Heavy Thunderstorms and Rain': 10,
    'Light Drizzle': 10,
    'Light Freezing Drizzle': 10,
    'Light Freezing Rain': 10,
    'Light Ice Pellets': 10,
    'Light Rain': 10,
    'Light Rain Showers': 10,
    'Light Snow': 10,
    'Light Snow Grains': 10,
    'Light Snow Showers': 10,
    'Light Thunderstorms and Rain': 10,
    'Low Drifting Snow': 10,
    'Rain': 10,
    'Rain Showers': 10,
    'Snow': 10,
    'Snow Showers': 10,
    'Thunderstorm': 10,
    'Thunderstorms and Rain': 10,
    'Blowing Snow': 10,
    'Chance of Snow': 10,
    'Freezing Rain': 10,
    'Unknown Precipitation': 10,
    'Overcast': 10,
    }

# List of precipitation conditions we don't want to water in, the conditions will be checked to see if they contain these phrases.

chkcond = [
    'flurries',
    'rain',
    'sleet',
    'snow',
    'storm',
    'hail',
    'ice',
    'squall',
    'precip',
    'funnel',
    'drizzle',
    'mist',
    'freezing',
    ]


# Get all data for the location this should only be called once, several functions below will handle the data

def getwuData():
    tloc = loc.split(',', 1)
    if key == '' or len(tloc) < 2:
        return 0
    #
    try:
        #req = requests.get('http://api.wunderground.com/api/' + key
        #                   + '/astronomy/yesterday/conditions/forecast/q/'
        #                    + loc + '.json')
        req = requests.get('http://mozart.uucp/data/' + key + '/' + loc + '.json')
        wuData = req.json()

        # Last chance to get that timezone information

        if tzone == None:
            offsets = getTZoneOffset(wuData['current_observation']['local_tz_long'])
        else:
            offsets = getTZoneOffset(tzone)
        #
        return (wuData, offsets)
    except:
        return ({}, {})
    #
#

# Grab the sunrise and sunset times in minutes from midnight

def getAstronomyData(data):
    if data:
        try:
            rHour = safe_int(data['sunrise']['hour'], 6)
            rMin  = safe_int(data['sunrise']['minute'])
            sHour = safe_int(data['sunset']['hour'], 18)
            sMin  = safe_int(data['sunset']['minute'])
            ## sunrise = (rHour*60)+rMin
            ## sunset  = (sHour*60)+sMin
            return {'rise': rHour * 60 + rMin, 'set': sHour * 60 + sMin}
        except:
            return {'rise': -1, 'set': -1}
        #
    #
#

# Calculate an adjustment based on predicted rainfall
# Rain forecast should lessen current watering and reduce rain water runoff, making the best use of rain.

def getForecastData(data):
    if data:
        nd = len(data)
        mm = [0.0] * nd
        cor = [0.0] * nd
        wfc = [0.0] * nd
        fadjust = [0.0] * nd
        try:
            for day in range(1, nd):
                mm[day] = data[day]['qpf_allday']['mm']
                cor[day] = data[day]['pop']
                wfc[day] = 1 / float(day ** 2)
                fadjust[day] = safe_float(mm[day], -1) \
                    * (safe_float(cor[day], -1) / 100) \
                    * safe_float(wfc[day], -1)
            #
        except:
            return -1
        #
        return sum(fadjust)
    #
#

# We need to know how much it rained yesterday and how much we watered versus how much we required

def mmFromLogs(t):
    ydate = (datetime.today() - datetime.utcfromtimestamp(0)).days - 1
    filenames = next(os.walk(logsPath))[2]
    for x in filenames:
        ldate = x
        if ldate == str(ydate):
            fpath = x
        #
    #
    yET = json.load(open(ETPath + '/' + fpath))
    tET = [0] * len(yET)
    logs = json.load(open(logsPath + '/' + fpath))
    if debug != 0: print >>sys.stderr, "E: json load %s/%s (%s)" % (logsPath, fpath, logs)
    l = len(t['mmTime'])
    ydur = [-1] * l
    ymm = [-1] * l
    for x in logs:
        if int(x[0]) == pid:
            ydur[safe_int(x[1])] += safe_int(x[2])
    for x in range(l):
        if t['mmTime'][x]:
            ymm[x] = round(safe_float(yET[safe_int(t['crop'][x])]) - ydur[x] / safe_float(t['mmTime'][x]), 4) * -1
            tET[int(t['crop'][x])] = ymm[x]
        else:
            ymm[x] = 0
    return (ymm, tET)
#

def writeResults(ET):
    data = json.load(open(WPPath + '/1mm'))
    try:
        minmax = json.load(open(WPPath + '/minmax'))
    except:
        minmax = [5, 15]
    fname = str((datetime.today() - datetime.utcfromtimestamp(0)).days)
    if data:
        try:
            runTime = []
            minRunmm = (min(minmax) if len(minmax) > 0 and min(minmax) >= 0 else 5)
            maxRunmm = (max(minmax) if len(minmax) > 1 and max(minmax) >= minRunmm else 15)
            times = 0
            (ymm, yET) = mmFromLogs(data)
            tET = [0] * len(ET)
            for x in range(len(ET)):
                ET[x] -= yET[x]
            for x in range(len(data['mmTime'])):
                aET = safe_float(ET[data['crop'][x]] - todayRain - ymm[x] - tadjust)
                times = int(max(min(aET / maxRunmm, 4), times))
                runTime.append(min(max(safe_int(data['mmTime'][x] * ((aET if aET >= minRunmm else 0)) * (not noWater)), 0), safe_int(data['mmTime'][x]) * maxRunmm))

            # #########################################
            # # Real logs will be written already    ##
            # #########################################

            with open(logsPath + '/' + fname, 'w') as f:
                logData = []
                for x in range(len(runTime)):
                    for y in range(times):
                        stnData = [pid, x, runTime[x]]
                        logData += [stnData]
                f.write(str(logData))
                f.close()
            try:
                stationID = wuData['current_observation']['station_id']
                print 'Weather Station ID:  ' + stationID
            except:
                print 'Problem opening log file ' + logsPath + '/' \
                    + fname + ' - 1'
                pass

            # #########################################
            # # Write final daily water balance      ##
            # #########################################

            with open(ETPath + '/' + fname, 'w') as f:
                f.write(str(ET))
                f.close()

            # ##########################################

            startTime = [-1] * 4
            availTimes = [sun['rise'] - sum(runTime) / 60, sun['rise'] + 60, sun['set'] - sum(runTime) / 60, sun['set'] + 60]
            for x in range(times):
                startTime[x] = availTimes[x]
            runTime = [startTime, runTime]
            print 'Current logged ET ' + str(ET)
            print data['mmTime']
            print runTime
            with open(WPPath + '/run', 'w') as f:
                f.write(str(runTime))
                f.close()
        except:
            tb = traceback.format_exc()
            print 'Problem opening ET file ' + ETPath + '/' + fname + ' - 1 (%s)' % (tb)
            pass
            print 'oops opening log file ' + fname + ' - 1'
#

# Let's check the current weather and make sure the wind is calm enough, it's not raining, and the temp is above freezing
# We will also look at what the rest of the day is supposed to look like, we want to stop watering if it is going to rain,
# or if the temperature will drop below freezing, as it would be bad for the pipes to contain water in these conditions.
# Windspeed for the rest of the day is used to determine best low wind watering time.

def getConditionsData(current, predicted):
    if current and predicted:
        try:
            cWeather = safe_float(conditions[current['weather']], 5)
        except:
            # pWeather = safe_float(conditions[predicted['conditions']],5)

            if any(x in current['weather'].lower() for x in chkcond):
                cWeather = 10
            else:
                print 'not found current ' + current['weather']
                cWeather = 5
            #
        #
        # if any(x in predicted['conditions'].lower() for x in chkcond):
        #     pWeather = 10
        # else:
        #     print 'not found predicted '+predicted['conditions']
        #     pWeather = 5
        # #

        cWind = wind_speed_2m(safe_float(current['wind_kph']), 10)
        cTemp = safe_float(current['temp_c'], 20)

        # current rain will only be used to adjust watering right before the start time

        cmm = safe_float(current['precip_today_metric'])
        pWind = wind_speed_2m(safe_float(predicted['avewind']['kph']),
                              10)
        pLowTemp = safe_float(predicted['low']['celsius'])
        pCoR = safe_float(predicted['pop']) / 100
        pmm = safe_float(predicted['qpf_allday']['mm'])

        # Let's check to see if it's raining, windy, or freezing.  Since watering is based on yesterday's data
        # we will see how much it rained today and how much it might rain later today.  This should
        # help reduce excess watering, without stopping water when little rain is forecast.

        try:
            nowater = 0
            whynot = ''
            if cWeather == 10 and current['weather'] != 'Overcast':
                nowater = 1
                whynot += 'precip (' + str(current['weather']) + ') '
            if cWind > pWind and pWind > 6 or cWind > 8:
                nowater = 1
                whynot += 'wind (' + str(round(cWind, 2)) + 'kph) '
            if cTemp < 4.5 or pLowTemp < 1:
                nowater = 1
                whynot += 'cold (' + str(round(cTemp, 2)) + 'C) '
            if pCoR:
                cmm += pmm * pCoR
        except:
            print 'we had a problem and just decided to water anyway'
            nowater = 0
        return (cmm, nowater, whynot)


def sun_block(sunrise, sunset):
    sh = 0
    for hour in range(sunrise / 60, sunset / 60 + 1):

        # Set a default value so we know we found missing data and can handle the gaps

        cloudCover = -1

        # Now let's find the data for each hour there are more periods than hours so only grab the first

        for period in range(len(wuData['history']['observations'])):
            if safe_int(wuData['history']['observations'][period]['date']['hour'], -1) == hour:
                if wuData['history']['observations'][period]['conds']:
                    try:
                        cloudCover = safe_float(conditions[wuData['history']['observations'][period]['conds']], 5) / 10
                        break
                    except KeyError:
                        cloudCover = 10
                        print 'Condition not found ' + wuData['history']['observations'][period]['conds']
                    #
                #
            #
        #
        # Found nothing, let's assume it was the same as last hour

        if cloudCover == -1:
            cloudCover = previousCloudCover
        #
        previousCloudCover = cloudCover

        # Got something now? let's check

        if cloudCover != -1:
            sh += 1 - cloudCover
        #
    #
    return sh
#

(wuData, offsets) = getwuData()
tadjust = getForecastData(wuData['forecast']['simpleforecast']['forecastday'])
sun     = getAstronomyData(wuData['sun_phase'])
(todayRain, noWater, whyNot) = getConditionsData(wuData['current_observation'], wuData['forecast']['simpleforecast']['forecastday'][0])

#########################Quick Ref Names For wuData#########################################

hist = wuData['history']['dailysummary'][0]

############################Required Data###################################################

lat = safe_float(lat)
tmin = safe_float(hist['mintempm'])
tmax = safe_float(hist['maxtempm'])
tmean = (tmin + tmax) / 2
alt = safe_float(wuData['current_observation']['display_location']['elevation'])
tdew = safe_float(hist['meandewptm'])
yDate = date(safe_int(hist['date']['year']), safe_int(hist['date']['mon']), safe_int(hist['date']['mday']))
doy = yDate.timetuple().tm_yday
sun_hours = sun_block(sun['rise'], sun['set'])
rh_min = safe_float(hist['minhumidity'])
rh_max = safe_float(hist['maxhumidity'])
rh_mean = (rh_min + rh_max) / 2
meanwindspeed = safe_float(hist['meanwindspdm'])
rainfall = min(safe_float(hist['precipm']), safe_float(rainfallsatpoint))

############################################################################################
##                             Calculations                                               ##
############################################################################################
# Calc Rn

e_tmin = delta_sat_vap_pres(tmin)
e_tmax = delta_sat_vap_pres(tmax)
sd = sol_dec(doy)
sha = sunset_hour_angle(lat, sd)
dl_hours = daylight_hours(sha)
irl = inv_rel_dist_earth_sun(doy)
etrad = et_rad(lat, sd, sha, irl)
cs_rad = clear_sky_rad(alt, etrad)
Ra = None
try:
    sol_rad = sol_rad_from_sun_hours(dl_hours, sun_hours, etrad)
except:
    try:
        sol_rad = sol_rad_from_t(etrad, cs_rad, tmin, tmax)
    except:
        try:
            print 'Data for Penman-Monteith ETo not available reverting to Hargreaves ETo'

            # Calc Ra

            Ra = etrad
        except:
            print 'Not enough data to complete calculations'
try:
    ea = ea_from_tdew(tdew)
except:
    try:
        ea = ea_from_tmin(tmin)
    except:
        try:
            ea = ea_from_rhmin_rhmax(e_tmin, e_tmax, rh_min, rh_max)
        except:
            try:
                ea = ea_from_rhmax(e_tmin, rh_max)
            except:
                try:
                    ea = ea_from_rhmean(e_tmin, e_tmax, rh_mean)
                except:
                    print 'Failed to set actual vapor pressure'
ni_sw_rad = net_in_sol_rad(sol_rad)
no_lw_rad = net_out_lw_rad(tmin, tmax, sol_rad, cs_rad, ea)
Rn = net_rad(ni_sw_rad, no_lw_rad)

# Calc t

t = (tmin + tmax) / 2

# Calc ws

ws = wind_speed_2m(meanwindspeed, 10)

# Calc es

es = mean_es(tmin, tmax)

# ea done in Rn calcs
# Calc delta_es

delta_es = delta_sat_vap_pres(t)

# Calc psy

atmospres = atmos_pres(alt)
psy = psy_const(atmospres)

###############################Print Results####################################

print str(round(tadjust, 4)) + ' mm precipitation forecast for next 3 days'  # tomorrow+2 days forecast rain
print str(round(todayRain, 4)) + ' mm precipitation fallen and forecast for today'  # rain fallen today + forecast rain for today
if noWater:  # Binary watering determination based on 3 criteria: 1)Currently raining 2)Wind>8kph~5mph 3)Temp<4.5C ~ 40F
    print 'We will not water because:  ' + whyNot
#
if not Ra:
    ETdailyG = round(ETo(Rn, t, ws, es, ea, delta_es, psy, 0)-rainfall,4) #ETo for most lawn grasses
    ETdailyS = round(ETo(Rn, t, ws, es, ea, delta_es, psy, 1)-rainfall,4) #ETo for decorative grasses, most shrubs and flowers
    print 'P-M ETo'
    print str(ETdailyG) + ' mm lost by grass'
    print str(ETdailyS) + ' mm lost by shrubs'
else:
    ETdailyG = ETdailyS = round(hargreaves_ETo(tmin, tmax, tmean, Ra) - rainfall, 4)
    print 'H ETo'
    print str(ETdaily) + ' mm lost today'
#
print 'sunrise & sunset in minutes from midnight local time'
print str(sun['rise']) + ' ' + str(sun['set'])
writeResults([ETdailyG, ETdailyS])
fname = str((datetime.today() - datetime.utcfromtimestamp(0)).days)
with open(wuDataPath+'/'+fname, 'w') as f:                               # today's (Epoch day) weather
    f.write(str(wuData['current_observation']['observation_epoch'])+'\t'+
            str(wuData['current_observation']['weather'])+'\t'+
            str(wuData['current_observation']['temp_f'])+'\t'+
            str(wuData['current_observation']['temp_c'])+'\t'+
            str(wuData['current_observation']['relative_humidity'])+'\t'+
            str(wuData['current_observation']['wind_degrees'])+'\t'+
            str(wuData['current_observation']['wind_mph'])+'\t'+
            str(wuData['current_observation']['wind_kph'])+'\t'+
            str(wuData['current_observation']['precip_1hr_in'])+'\t'+
            str(wuData['current_observation']['precip_1hr_metric'])+'\t'+
            str(wuData['current_observation']['precip_today_string'])+'\t'+
            str(wuData['current_observation']['precip_today_in'])+'\t'+
            str(wuData['current_observation']['precip_today_metric'])+'\t'+
            str(noWater))
    f.close()
#

# -[ fini ]---------------------------------------------------------------------

##Functions
##---------
##Atmospheric pressure (P):
##    atmos_pres(alt)
##Actual vapour pressure (ea):
##    ea_from_tdew(tdew)
##    ea_from_twet_tdry(twet, tdry, e_twet, psy_const)
##    ea_from_rhmin_rhmax(e_tmin, e_tmax, rh_min, rh_max)
##    ea_from_rhmax(e_tmin, rh_max)
##    ea_from_rhmean(e_tmin, e_tmax, rh_mean)
##    ea_from_tmin(tmin)
##Evapotranspiration over grass or shrubs (ETo):
##    ETo(Rn, t, ws, es, ea, delta_es, psy, crop=0, shf=0.0)
##    hargreaves_ETo(tmin, tmax, tmean, Ra)
##Pyschrometric constant:
##    psy_const(atmos_pres)
##    psy_const_of_psychrometer(psychrometer, atmos_pres)
##Radiation:
##    sol_rad_from_sun_hours(dl_hours, sun_hours, et_rad)
##    sol_rad_from_t(et_rad, cs_rad, tmin, tmax, coastal=-999)
##    sol_rad_island(et_rad) -only useful for monthly calculations
##    net_rad(ni_sw_rad, no_lw_rad)
##    clear_sky_rad(alt, et_rad)
##    daylight_hours(sha)
##    net_in_sol_rad(sol_rad)
##    net_out_lw_rad(tmin, tmax, sol_rad, clear_sky_rad, ea)
##    rad2equiv_evap(energy)
##    et_rad(lat, sd, sha, irl)
##Relative humidity (RH):
##    rh_from_ea_es(ea, es)
##Saturated vapour pressure (es):
##    delta_sat_vap_pres(t)
##    mean_es(tmin, tmax)
##Soil heat flux:
##    daily_soil_heat_flux(t_cur, t_prev, delta_t, soil_heat_cap=2.1, delta_z=0.10)
##Solar angles etc:
##    inv_rel_dist_earth_sun(doy)
##    sol_dec(doy)
##    sunset_hour_angle(lat, sd)
##Temperature:
##    daily_mean_t(tmin, tmax)
##Wind speed:
##    wind_speed_2m(meas_ws, z)

# -[ Notes ]--------------------------------------------------------------------
# https://opensprinkler.com/forums/topic/penmen-monteith-eto-method-python-script-for-possible-use-as-weather-script/
# https://www.hackster.io/Dan/particle-photon-weather-station-462217
# http://www.wunderground.com/weather/api/d/docs?d=resources/phrase-glossary
# http://www.fao.org/docrep/x0490e/x0490e08.htm (Chapter 4 - Determination of ETo)
# http://httpbin.org/
# ------------------------------------------------------------------------------
