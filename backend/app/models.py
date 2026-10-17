"""Request models preserve the frontend's camelCase API contract."""
import math
from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictStr, model_validator


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError('Enter a valid number.')
    try:
        result = float(value)
    except ValueError:
        raise ValueError('Enter a valid number.') from None
    if not math.isfinite(result):
        raise ValueError('Enter a finite number.')
    return result


def optional_number(value):
    return None if value is None or value == '' else number(value)

Number = Annotated[float, BeforeValidator(number)]
OptionalNumber = Annotated[float | None, BeforeValidator(optional_number)]
Text = Annotated[str, Field(strict=True, max_length=100)]

class PhoneRequest(BaseModel):
    phone: StrictStr = Field(max_length=30)

class VerifyRequest(PhoneRequest):
    otp: StrictStr = Field(pattern=r'^[0-9]{6}$')

class Farm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='ignore', allow_inf_nan=False)
    farmerName: Text = Field(min_length=1)
    farmName: Text = ''
    village: Text = ''
    district: Text = ''
    state: Text = ''
    latitude: OptionalNumber = Field(default=None, ge=-90, le=90)
    longitude: OptionalNumber = Field(default=None, ge=-180, le=180)
    area: Number = Field(gt=0, le=1000000)
    unit: Literal['acres', 'hectares']
    soilType: Literal['sandy', 'clay', 'loamy', 'silty', 'other', 'I don’t know']
    water: Literal['rainfed', 'reliable irrigation', 'limited irrigation']
    previousCrop: Text = ''
    sowingMonth: Literal['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    ph: OptionalNumber = Field(default=None, ge=0, le=14)
    nitrogen: OptionalNumber = Field(default=None, ge=0, le=100000)
    phosphorus: OptionalNumber = Field(default=None, ge=0, le=100000)
    potassium: OptionalNumber = Field(default=None, ge=0, le=100000)
    npkUnit: Literal['', 'kg/ha', 'mg/kg', 'ppm'] = ''

    @model_validator(mode='after')
    def location_and_units(self):
        manual = self.village and self.district and self.state
        coordinates = self.latitude is not None and self.longitude is not None
        if not manual and not coordinates:
            raise ValueError('Enter village, district and state, or both coordinates.')
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Enter both latitude and longitude.')
        if any(value is not None for value in (self.nitrogen, self.phosphorus, self.potassium)) and not self.npkUnit:
            raise ValueError('Select a unit for NPK values.')
        return self
