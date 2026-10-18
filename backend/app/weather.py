"""Fixed Open-Meteo endpoint: no arbitrary URLs or credentials."""
import math
import httpx2 as httpx
from fastapi import HTTPException

async def weather(latitude, longitude):
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get('https://api.open-meteo.com/v1/forecast', params={
                'latitude': latitude, 'longitude': longitude,
                'current': 'temperature_2m,relative_humidity_2m,rain',
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum',
                'forecast_days': 7, 'timezone': 'auto'})
            response.raise_for_status()
            data = response.json()
        current = data['current']
        for key in ['temperature_2m', 'relative_humidity_2m', 'rain']:
            if not isinstance(current[key], (int, float)) or not math.isfinite(current[key]):
                raise ValueError('Missing weather value')
        daily = data['daily']
        if not all(isinstance(daily[k], list) and len(daily[k]) == len(daily['time']) for k in ['time', 'temperature_2m_max', 'temperature_2m_min', 'precipitation_sum']):
            raise ValueError('Incomplete forecast')
        for key in ['temperature_2m_max', 'temperature_2m_min', 'precipitation_sum']:
            if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in daily[key]):
                raise ValueError('Missing forecast values')
        return {'source': 'Open-Meteo', 'attribution': 'https://open-meteo.com/',
                'provenance': 'weather-estimate', 'latitude': data['latitude'], 'longitude': data['longitude'],
                'timezone': data['timezone'], 'current': current, 'currentUnits': data['current_units'],
                'forecast': daily, 'forecastUnits': data['daily_units'],
                'rainfallNote': 'Current rain and seven-day forecast precipitation are not historical or seasonal rainfall. Rainfall is not auto-filled into the crop model.'}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(502, 'Weather service unavailable or returned incomplete data. Enter values manually.') from None
