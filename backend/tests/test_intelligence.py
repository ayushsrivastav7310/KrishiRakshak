import io
import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from app.api import create_app
from app.intelligence import ModelRegistry, validated_image
from test_api import CONFIG, ORIGIN, login

VALUES = dict(N=90,P=42,K=43,temperature=20.88,humidity=82,ph=6.5,rainfall=202)

@pytest.fixture
def client(tmp_path):
    app = create_app({**CONFIG, 'UPLOAD_DIR': str(tmp_path / 'uploads')})
    with TestClient(app, headers={'Origin': ORIGIN}) as client:
        yield app, client

def photo():
    out = io.BytesIO()
    Image.new('RGB', (224,224), 'brown').save(out,format='PNG')
    return out.getvalue()

@pytest.mark.parametrize('data,mime', [(b'not image','image/png'), (photo(),'image/jpeg'), (b'a'*(5*1024*1024+1),'image/png'), (b'<svg/>','image/svg+xml')], ids=['corrupt','mime-mismatch','too-large','svg'])
def test_image_validation(data,mime):
    with pytest.raises(HTTPException) as error:
        validated_image(data,mime)
    assert error.value.status_code == 400

def test_valid_image_and_decompression_limit():
    assert validated_image(photo(),'image/png').size == (224,224)
    out = io.BytesIO()
    Image.new('RGB',(5000,4001)).save(out,format='PNG')
    with pytest.raises(HTTPException):
        validated_image(out.getvalue(),'image/png')

def test_unavailable_and_corrupt_models(tmp_path):
    registry = ModelRegistry(tmp_path)
    assert not registry.metadata()['crop']['available']
    with pytest.raises(HTTPException) as error:
        registry.require('soil')
    assert error.value.status_code == 503
    (tmp_path/'crop.json').write_text('broken')
    assert ModelRegistry(tmp_path).errors['crop'] == 'JSONDecodeError'

def test_authentication_and_missing_models(tmp_path):
    app=create_app({**CONFIG,'UPLOAD_DIR':str(tmp_path/'uploads'),'MODEL_DIR':str(tmp_path/'missing')})
    with TestClient(app,headers={'Origin':ORIGIN}) as c:
        for endpoint in ['/models/metadata','/crops/supported','/intelligence/history','/weather?latitude=1&longitude=1']:
            assert c.get('/api'+endpoint).status_code==401
        assert c.post('/api/crops/recommend',json=VALUES).status_code==401
        login(c)
        assert c.post('/api/crops/recommend',json=VALUES).status_code==503
        assert c.post('/api/soil/predict',files={'photo':('soil.png',photo(),'image/png')}).status_code==503
        assert c.get('/api/intelligence/history').json()['history']==[]

@pytest.mark.parametrize('changes',[{'N':-1},{'P':True},{'ph':15},{'humidity':101},{'rainfall':-1},{'temperature':66},{'N':'NaN'},{'N':None},{'unexpected':1}])
def test_invalid_crop_values(client,changes):
    _,c=client
    login(c)
    assert c.post('/api/crops/recommend',json={**VALUES,**changes}).status_code==400

def test_real_models_predictions_and_owner_history(client):
    app,c=client
    assert app.state.models.metadata()['crop']['available'], 'Run train_crop.py before integration tests'
    assert app.state.models.metadata()['soil']['available'], 'Run fetch_sources.py and prepare_soil.py before integration tests'
    login(c)
    assert c.get('/api/crops/supported').json()['soilTypeUsed'] is False
    result=c.post('/api/crops/recommend',json=VALUES)
    assert result.status_code==200,result.text
    result=result.json()
    assert result['recommendedCrop']=='rice'
    assert result['inputs']['N']==90
    assert 0<=result['suggestions'][0]['score']<=1
    assert c.post('/api/crops/recommend',json={**VALUES,'N':999}).status_code==400
    soil=c.post('/api/soil/predict',files={'photo':('soil.png',photo(),'image/png')})
    assert soil.status_code==200,soil.text
    soil=soil.json()
    assert soil['soilType'] in soil['supportedClasses']
    assert 0<=soil['confidence']<=1
    assert c.post('/api/soil/correction',json={'analysisId':soil['id'],'soilType':'Loamy'}).status_code==200
    assert len(c.get('/api/intelligence/history').json()['history'])==3
    assert not list(app.state.settings.upload_dir.iterdir())
    login(c,'+919876543211')
    assert c.get('/api/intelligence/history').json()['history']==[]
    assert c.post('/api/soil/correction',json={'analysisId':soil['id'],'soilType':'Clay'}).status_code==404

def test_history_survives_restart(tmp_path):
    config={**CONFIG,'DATABASE_PATH':str(tmp_path/'history.sqlite'),'UPLOAD_DIR':str(tmp_path/'uploads')}
    for iteration in range(2):
        app=create_app(config)
        with TestClient(app,headers={'Origin':ORIGIN}) as c:
            if iteration==0:
                login(c)
                token=c.cookies.get('session')
                assert c.post('/api/crops/recommend',json=VALUES).status_code==200
            else:
                c.cookies.set('session',token)
                assert c.get('/api/intelligence/history').json()['history'][0]['result']['recommendedCrop']=='rice'

def test_weather_errors_and_validation(client,monkeypatch):
    _,c=client
    login(c)
    import app.weather as module
    class FailedClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,*args,**kwargs): raise module.httpx.ConnectError('offline')
    monkeypatch.setattr(module.httpx,'AsyncClient',FailedClient)
    assert c.get('/api/weather?latitude=91&longitude=0').status_code==400
    assert c.get('/api/weather?latitude=NaN&longitude=0').status_code==400
    assert c.get('/api/weather?latitude=26&longitude=80').status_code==502

def test_weather_mapping(client,monkeypatch):
    _,c=client
    login(c)
    import app.weather as module
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'latitude':26,'longitude':80,'timezone':'Asia/Kolkata','current':{'temperature_2m':25,'relative_humidity_2m':60,'rain':1,'time':'2026-10-18T00:00'},'current_units':{},'daily_units':{},'daily':{'time':['2026-10-18'],'temperature_2m_max':[29],'temperature_2m_min':[20],'precipitation_sum':[2]}}
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,url,params):
            assert url=='https://api.open-meteo.com/v1/forecast'
            return Response()
    monkeypatch.setattr(module.httpx,'AsyncClient',Client)
    result=c.get('/api/weather?latitude=26&longitude=80')
    assert result.status_code==200
    assert result.json()['provenance']=='weather-estimate'
    assert 'not historical' in result.json()['rainfallNote']
