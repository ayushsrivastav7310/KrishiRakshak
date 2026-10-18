import io
import pytest
from PIL import Image
from app.diseases import DiseaseModel
from test_api import api, login
from datetime import date
from app.irrigation import IrrigationInput, calculate
from app.mandi import parse_price, ingest, prices, Comparison, compare, import_msp
from app.database import Database
from app.phase_store import migrate
from fastapi import HTTPException
from app.mandi import MandiService
import asyncio

def test_sync_credentials_and_outage(monkeypatch):
    import app.mandi as module
    db=Database(':memory:');migrate(db)
    class Response:
        status_code=403
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):return Response()
    monkeypatch.setenv('DATA_GOV_API_KEY','test-only-key')
    monkeypatch.setattr(module.httpx,'AsyncClient',Client)
    with pytest.raises(HTTPException) as error:asyncio.run(MandiService(db).sync())
    assert error.value.status_code==502
    db.close()

def test_weather_parsing_and_incomplete(monkeypatch):
    import app.irrigation as module
    module._cache.clear()
    payload={'daily':{'time':[str(date.today())],'et0_fao_evapotranspiration':[4.0],'precipitation_sum':[0.0]},'daily_units':{'et0_fao_evapotranspiration':'mm','precipitation_sum':'mm'}}
    class Response:
        def raise_for_status(self):pass
        def json(self):return payload
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):return Response()
    monkeypatch.setattr(module.httpx,'AsyncClient',Client)
    assert asyncio.run(module.irrigation_weather(26,80))['daily']['et0_fao_evapotranspiration']==[4]
    module._cache.clear();payload['daily']['precipitation_sum']=[None]
    with pytest.raises(HTTPException):asyncio.run(module.irrigation_weather(26,80))

PRICE={'state':'Uttar Pradesh','district':'Lucknow','market':'Lucknow','commodity':'Wheat','variety':'Other','arrival_date':'01/10/2026','min_price':'2000','max_price':'2500','modal_price':'2300'}

def test_market_import_dedup_normalization_and_costs():
    db=Database(':memory:'); migrate(db)
    ingest(db,[PRICE,PRICE]); result=prices(db)
    assert result['total']==1
    row=result['records'][0]
    assert row['stale'] is True
    assert parse_price(PRICE,unit='INR/kg')[8]==230000
    body=Comparison(commodity='Wheat',variety='Other',quantityQuintals=2,options=[{'priceId':row['id'],'distanceKm':20,'transportPerKm':10,'handlingCost':100}])
    assert compare(db,body)['options'][0]['net']==4300
    assert prices(db,commodity='Rice')['records']==[]
    db.close()

@pytest.mark.parametrize('change',[{'modal_price':'NaN'},{'min_price':'3000'},{'arrival_date':'wrong'}])
def test_market_invalid(change):
    with pytest.raises(ValueError):parse_price(PRICE|change)

def test_msp_matching_and_source():
    db=Database(':memory:');migrate(db)
    row={'crop':'Wheat','variety':'Other','season':'2026-27','price':'2425','unit':'INR/quintal','source':'https://desagri.gov.in/notification-test','period_start':'2026-04-01','period_end':'2027-03-31'}
    # Synthetic values are test fixtures only; never seed production data.
    assert import_msp(db,[row])==1
    with pytest.raises(ValueError):import_msp(db,[row|{'source':'https://example.com'}])
    db.close()

def test_market_endpoints_and_missing_key(api,monkeypatch):
    monkeypatch.delenv('DATA_GOV_API_KEY',raising=False)
    app,client=api;login(client)
    assert client.get('/api/mandi/prices').json()['total']==0
    assert client.post('/api/mandi/sync').status_code==503
    assert client.get('/api/mandi/sync-status').json()['count']==0
    assert client.get('/api/mandi/msp?crop=Wheat&variety=Other&season=2026-27').json()['records']==[]

def test_irrigation_balance_and_missing():
    base = dict(crop='maize',latitude=26,longitude=80,areaM2=1000,plantingDate=str(date.today()))
    weather = {'daily':{'time':[str(date.today())],'et0_fao_evapotranspiration':[5],'precipitation_sum':[0]}}
    assert calculate(IrrigationInput(**base),weather)['depthMm'] is None
    full = IrrigationInput(**base,fieldCapacity=.3,wiltingPoint=.1,rootDepthM=1,depletionMm=100,efficiency=1)
    result = calculate(full,weather)
    assert result['depthMm'] == 101.5
    assert result['volumeLiters'] == 101500
    weather['daily']['precipitation_sum']=[100]
    assert calculate(full,weather)['depthMm'] == 0

def test_irrigation_stage_handling():
    from datetime import timedelta
    base=dict(crop='maize',latitude=26,longitude=80,areaM2=1000)
    weather={'daily':{'time':[str(date.today())],'et0_fao_evapotranspiration':[5],'precipitation_sum':[0]}}
    result=calculate(IrrigationInput(**base,plantingDate=date.today()-timedelta(days=65)),weather)
    assert result['stage']=='mid-season' and result['kc']==1.2

@pytest.mark.parametrize('change',[{'areaM2':0},{'areaM2':float('nan')},{'fieldCapacity':.1,'wiltingPoint':.3}])
def test_irrigation_validation(change):
    with pytest.raises(ValueError):
        IrrigationInput(**(dict(crop='maize',latitude=1,longitude=1,areaM2=100,plantingDate=str(date.today()))|change))

def test_irrigation_log_history(api):
    app,client=api; login(client)
    response=client.post('/api/irrigation/log',json={'crop':'maize','date':str(date.today()),'depthMm':10,'areaM2':100})
    assert response.status_code==200,response.text
    assert response.json()['volumeLiters']==1000
    assert len(client.get('/api/irrigation/history').json()['history'])==1

def test_disease_unavailable_and_upload(api):
    app, client = api
    assert client.get('/api/diseases/history').status_code == 401
    login(client)
    assert client.post('/api/diseases/predict',data={'crop':'Tomato'},files={'photo':('x.png',b'bad','image/png')}).status_code == 400
    assert 'available' in client.get('/api/diseases/model-info').json()
    assert client.get('/api/diseases/history').json()['history'] == []

def test_disease_missing(tmp_path):
    model = DiseaseModel(tmp_path)
    assert model.info()['available'] is False
    with pytest.raises(Exception) as exc: model.predict(Image.new('RGB',(224,224)),'Tomato')
    assert exc.value.status_code == 503

def test_real_disease_inference_and_history(api):
    app,client=api;login(client)
    info=client.get('/api/diseases/model-info').json()
    if not info['available']: pytest.skip('Verified disease model not installed')
    data=io.BytesIO();Image.new('RGB',(256,256),'green').save(data,format='PNG')
    response=client.post('/api/diseases/predict',data={'crop':'Tomato'},files={'photo':('leaf.png',data.getvalue(),'image/png')})
    assert response.status_code==200,response.text
    result=response.json()
    assert 0<=result['confidence']<=1 and result['modelVersion']==info['version']
    assert len(result['alternatives'])==3
    assert len(client.get('/api/diseases/history').json()['history'])==1
    assert result['imageUnclear'] is True and result['uncertain'] is True
    login(client,phone='+919876543211')
    assert client.get('/api/diseases/history').json()['history']==[]
    # This verifies actual model execution, not diagnostic correctness on a synthetic image.
