"""Daily bucket water balance inspired by FAO-56, not a calibrated field model."""
from datetime import date, timedelta
import math
import time
import httpx2 as httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

class IrrigationInput(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    fieldId: str = Field(default='main',min_length=1,max_length=80)
    crop: Literal['maize','wheat','tomato']
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)
    areaM2: float = Field(gt=0,le=100000000)
    plantingDate: date
    soilType: str = Field(default='unknown',max_length=80)
    # Explicit water retention inputs; never derived from a soil photo.
    fieldCapacity: float | None = Field(default=None,gt=0,le=.7)
    wiltingPoint: float | None = Field(default=None,ge=0,lt=.7)
    rootDepthM: float | None = Field(default=None,gt=0,le=3)
    depletionMm: float | None = Field(default=None,ge=0,le=2000)
    moisture: float | None = Field(default=None,ge=0,le=.7)
    lastIrrigationDate: date | None = None
    recentIrrigationMm: float = Field(default=0,ge=0,le=1000)
    efficiency: float = Field(default=.8,gt=0,le=1)
    @model_validator(mode='after')
    def dates_and_soil(self):
        if self.plantingDate > date.today() or (self.lastIrrigationDate and self.lastIrrigationDate > date.today()):
            raise ValueError('Dates must not be in the future')
        if self.fieldCapacity is not None and self.wiltingPoint is not None and self.fieldCapacity <= self.wiltingPoint:
            raise ValueError('Field capacity must exceed wilting point')
        return self

class IrrigationLog(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False)
    fieldId: str = Field(default='main',min_length=1,max_length=80)
    crop: str = Field(min_length=1,max_length=80)
    date: date
    depthMm: float = Field(gt=0,le=1000)
    areaM2: float = Field(gt=0,le=100000000)
    @model_validator(mode='after')
    def past(self):
        if self.date > date.today(): raise ValueError('Cannot record future irrigation')
        return self

_cache = {}
async def irrigation_weather(latitude,longitude):
    key = (round(latitude,4),round(longitude,4))
    if key in _cache and time.monotonic()-_cache[key][0] < 900: return _cache[key][1]
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get('https://api.open-meteo.com/v1/forecast',params={
                'latitude':latitude,'longitude':longitude,'timezone':'auto','forecast_days':7,
                'current':'temperature_2m,relative_humidity_2m,wind_speed_10m',
                'daily':'precipitation_sum,et0_fao_evapotranspiration',
                'hourly':'soil_moisture_0_to_1cm,soil_temperature_0cm,shortwave_radiation'})
            response.raise_for_status(); data = response.json()
        daily = data['daily']; units = data['daily_units']
        if units['precipitation_sum'] != 'mm' or units['et0_fao_evapotranspiration'] != 'mm': raise ValueError()
        n = len(daily['time'])
        if n < 1: raise ValueError()
        for field in ['precipitation_sum','et0_fao_evapotranspiration']:
            if len(daily[field]) != n or not all(isinstance(v,(float,int)) and math.isfinite(v) and v>=0 for v in daily[field]): raise ValueError()
        result = {'source':'Open-Meteo','sourceUrl':'https://open-meteo.com/en/docs','fetchedAt':time.time(),
                  'daily':daily,'units':units,'current':data.get('current'), 'currentUnits':data.get('current_units'),
                  'hourly':data.get('hourly'),'hourlyUnits':data.get('hourly_units'),
                  'warning':'Forecast and soil moisture are modeled estimates, not sensor measurements. Surface moisture is not root-zone water status.'}
        if len(_cache)>=128: _cache.clear()
        _cache[key]=(time.monotonic(),result)
        return result
    except (httpx.HTTPError,ValueError,KeyError,TypeError):
        raise HTTPException(502,'Irrigation weather unavailable or incomplete; no quantity calculated.') from None

# FAO-56 Table 12 indicative Kc values. Stage durations are explicit planning assumptions.
COEFFICIENTS = {'maize':(1.2,.6,125), 'wheat':(1.15,.3,150), 'tomato':(1.15,.8,135)}
def calculate(body, weather):
    mid, end, duration = COEFFICIENTS[body.crop]
    age = (date.today()-body.plantingDate).days
    fraction = age/duration
    if fraction < .2: stage,kc = 'initial',.3 if body.crop!='tomato' else .6
    elif fraction < .4:
        initial = .6 if body.crop=='tomato' else .3
        stage,kc = 'development',initial+(mid-initial)*(fraction-.2)/.2
    elif fraction < .8: stage,kc = 'mid-season',mid
    else: stage,kc = 'late-season',mid+(end-mid)*min(1,(fraction-.8)/.2)
    warnings = ['Kc and stage durations are indicative assumptions; adjust with local agronomic advice.',
                'Effective rain assumed 80%; runoff, deep drainage and capillary rise are not calibrated.',
                'Water status must describe today before any recent irrigation entered below. Past irrigation dates alone cannot reconstruct depletion.']
    result = {'crop':body.crop,'fieldId':body.fieldId,'stage':stage,'kc':round(kc,3),'weather':weather,
              'source':'FAO-56 simplified daily water balance','sourceUrl':'https://www.fao.org/4/x0490e/x0490e00.htm',
              'warnings':warnings,'depthMm':None,'volumeLiters':None,'suggestedDate':None,'calendar':[]}
    if any(v is None for v in [body.fieldCapacity,body.wiltingPoint,body.rootDepthM]) or (body.depletionMm is None and body.moisture is None):
        warnings.append('Missing root-zone retention or current water status. No precise irrigation quantity can be recommended.')
        return result
    taw = 1000*(body.fieldCapacity-body.wiltingPoint)*body.rootDepthM
    depletion = body.depletionMm if body.depletionMm is not None else 1000*(body.fieldCapacity-body.moisture)*body.rootDepthM
    if depletion > taw: warnings.append('Water depletion exceeds available water; clamped to estimated capacity.')
    depletion = max(0,min(taw,depletion)-body.recentIrrigationMm*body.efficiency)
    if age > duration:
        warnings.append('Crop is beyond assumed season duration; confirm crop stage before calculating irrigation.')
        return result
    threshold = .5*taw
    for day, et0, rain in zip(weather['daily']['time'],weather['daily']['et0_fao_evapotranspiration'],weather['daily']['precipitation_sum']):
        etc=kc*et0
        depletion=max(0,min(taw,depletion+etc-.8*rain))
        net = depletion if depletion>=threshold else 0
        gross = net/body.efficiency
        result['calendar'].append({'date':day,'etcMm':round(etc,2),'rainMm':rain,'estimatedDepletionMm':round(depletion,2),'depthMm':round(gross,2)})
        if net and result['suggestedDate'] is None:
            result.update(suggestedDate=day,depthMm=round(gross,2),volumeLiters=round(gross*body.areaM2))
        if net: depletion=0
    if result['suggestedDate'] is None: result.update(depthMm=0,volumeLiters=0)
    result['explanation']='Irrigate when estimated depletion reaches 50% of total available root-zone water. Gross depth accounts for application efficiency.'
    return result
