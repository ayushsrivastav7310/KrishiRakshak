import base64
import hashlib
import hmac
import time
from urllib.parse import urlencode
from xml.etree.ElementTree import fromstring

import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.voice import intent, number, twiml
from test_api import CONFIG, ORIGIN, login, FARM

PUBLIC = 'https://voice.example.com'
TOKEN = 'test-twilio-token'
SID = 'CA' + 'a'*32
ACCOUNT = 'AC' + 'b'*32
PHONE = '+919876543210'
TO = '+15005550006'

@pytest.fixture
def voice(tmp_path):
    app = create_app({**CONFIG, 'UPLOAD_DIR': str(tmp_path/'uploads'), 'MODEL_DIR': str(tmp_path/'models'),
                      'VOICE_ENABLED': 'true', 'VOICE_PUBLIC_URL': PUBLIC,
                      'TWILIO_AUTH_TOKEN': TOKEN, 'TWILIO_ACCOUNT_SID': ACCOUNT, 'TWILIO_PHONE_NUMBER': TO})
    with TestClient(app, headers={'Origin': ORIGIN}) as c:
        login(c)
        assert c.put('/api/voice/profile', json={'pin':'123456','consent':True}).status_code == 200
        yield app, c

def hook(c, path, **fields):
    data = {'AccountSid':ACCOUNT, 'CallSid':SID, 'From':PHONE, 'To':TO, **fields}
    material = PUBLIC+path+''.join(k+str(v) for k,v in sorted(data.items()))
    sig = base64.b64encode(hmac.new(TOKEN.encode(),material.encode(),hashlib.sha1).digest()).decode()
    return c.post(path, content=urlencode(data), headers={'Origin':'', 'Content-Type':'application/x-www-form-urlencoded','X-Twilio-Signature':sig})

def enroll(c, **extra):
    return c.put('/api/voice/profile',json={'pin':'123456','consent':True,**extra})

def simulate(c, cid=None, text=''):
    r = c.post('/api/voice/simulate',json={'callId':cid,'text':text})
    assert r.status_code == 200, r.text
    return r.json()

def test_hindi_intents_numeric_and_xml():
    assert intent('फसल की सलाह') == 'crop'
    assert intent('पानी कब दें') == 'irrigation'
    assert intent('मंडी में फसल का भाव') is None  # ambiguous -> keypad fallback
    assert number('६*५') == 6.5
    with pytest.raises(ValueError): number('10 या 20')
    root = fromstring(twiml('मूल्य < 10 & सुरक्षित', 'https://host/input?step=2'))
    assert root.find('Gather').attrib['language'] == 'hi-IN'
    assert root.find('.//Say').text == 'मूल्य < 10 & सुरक्षित'

def test_provider_configuration_signature_and_browser_csrf(voice):
    app,c = voice
    assert c.get('/api/voice/config').json()['configured'] is True
    assert c.post('/voice/twilio/incoming',data={'CallSid':SID}).status_code == 403
    assert hook(c,'/voice/twilio/incoming',AccountSid='wrong').status_code == 403
    assert hook(c,'/voice/twilio/incoming',To='+15005550007').status_code == 403
    assert c.post('/api/voice/simulate',json={},headers={'Origin':''}).status_code == 403
    c.cookies.clear()
    assert c.get('/api/voice/calls').status_code == 401

def test_pin_flow_replay_stale_steps_no_pin_in_history(voice):
    app,c = voice
    r = hook(c,'/voice/twilio/incoming')
    assert r.status_code == 200 and 'numDigits="6"' in r.text
    r = hook(c,'/voice/twilio/input?step=0',Digits='123456')
    assert r.status_code == 200 and 'speech dtmf' in r.text
    assert hook(c,'/voice/twilio/input?step=0',Digits='123456').text == r.text
    assert hook(c,'/voice/twilio/input?step=99',Digits='1').status_code == 409
    hook(c,'/voice/twilio/input?step=1',Digits='3')
    hook(c,'/voice/twilio/input?step=2',Digits='1')
    calls=c.get('/api/voice/calls').json()['calls']
    assert len(calls[0]['turns']) == 2
    assert '123456' not in c.get('/api/voice/calls').text
    assert 'pin_hash' not in c.get('/api/voice/config').text
    assert hook(c,'/voice/twilio/status',CallStatus='completed').status_code == 204
    assert c.get('/api/voice/calls').json()['calls'][0]['status'] == 'completed'
    assert '<Hangup' in hook(c,'/voice/twilio/input?step=2',Digits='1').text

def test_pin_lockout_across_calls_and_revocation(voice):
    app,c = voice
    for i in range(2):
        sid='CA'+str(i)*32
        hook(c,'/voice/twilio/incoming',CallSid=sid)
        for step in range(3):
            hook(c,f'/voice/twilio/input?step={step}',CallSid=sid,Digits='000000')
    with app.state.database.lock:
        p=app.state.database.connection.execute('SELECT * FROM voice_profiles').fetchone()
        assert p['locked_until'] > time.time()
        assert p['pin_hash'] != '123456'
    enroll(c)
    hook(c,'/voice/twilio/incoming')
    hook(c,'/voice/twilio/input?step=0',Digits='123456')
    enroll(c)
    assert '<Hangup' in hook(c,'/voice/twilio/input?step=1',Digits='1').text

def test_crop_collects_all_measurements_and_uses_model(voice,monkeypatch):
    app,c = voice
    seen=[]
    monkeypatch.setattr(app.state.models,'crop',lambda body:(seen.append(body.model_dump()) or {'recommendedCrop':'rice'}))
    call=simulate(c)
    cid=call['id']
    assert 'नाइट्रोजन' in simulate(c,cid,'1')['message']
    assert 'मान समझ नहीं' in simulate(c,cid,'9000')['message']
    for value in ['0','40','40','25','70','६*५','100']:
        call=simulate(c,cid,value)
    assert seen[0]['N']==0 and seen[0]['ph']==6.5
    assert 'rice' in call['message']
    assert simulate(c,cid,'0')['status']=='completed'

def test_missing_data_and_mandi_reuses_official_records(voice):
    app,c=voice
    cid=simulate(c)['id']
    assert 'बिना माप' in simulate(c,cid,'2')['message']
    c.put('/api/farm',json=FARM)
    simulate(c,cid,'3')
    assert 'उपलब्ध नहीं' in simulate(c,cid,'1')['message']
    from app.mandi import ingest
    # Synthetic test fixture only; never seed the real database.
    row={'state':FARM['state'],'district':FARM['district'],'market':'Lucknow','commodity':'Wheat','variety':'Other',
         'arrival_date':'2020-01-01','min_price':'1000','modal_price':'1500','max_price':'2000'}
    ingest(app.state.database,[row])
    simulate(c,cid,'3')
    answer=simulate(c,cid,'1')['message']
    assert '1500' in answer and 'प्रति क्विंटल' in answer and 'पुराना' in answer
    assert '2020-01-01' in answer

def test_irrigation_service_and_silence_limits(voice,monkeypatch):
    app,c=voice
    from datetime import date
    inputs={'crop':'wheat','plantingDate':date.today().isoformat(),'areaM2':1000,'latitude':26,'longitude':80,
            'fieldCapacity':.3,'wiltingPoint':.1,'rootDepthM':1,'depletionMm':150}
    assert enroll(c,irrigation=inputs).status_code==200
    async def weather(*args):
        return {'daily':{'time':[date.today().isoformat()],'precipitation_sum':[0],'et0_fao_evapotranspiration':[5]}}
    monkeypatch.setattr('app.voice.irrigation_weather',weather)
    cid=simulate(c)['id']
    assert 'लीटर' in simulate(c,cid,'सिंचाई')['message']
    cid=simulate(c)['id']
    for _ in range(3): call=simulate(c,cid,'')
    assert call['status']=='completed'

def test_owner_isolation_consent_delete_and_expiry(voice):
    app,c=voice
    cid=simulate(c)['id']
    with app.state.database.lock, app.state.database.connection:
        app.state.database.connection.execute('UPDATE voice_calls SET created=? WHERE id=?',(time.time()-901,cid))
    assert simulate(c,cid,'1')['status']=='completed'
    assert enroll(c,consent=False).status_code==400
    c.cookies.clear();login(c,'+919876543211')
    assert c.get('/api/voice/calls').json()['calls']==[]
    enroll(c)
    assert c.post('/api/voice/simulate',json={'callId':cid,'text':'1'}).status_code==404
    own=simulate(c)
    assert c.delete('/api/voice/profile').status_code==200
    assert c.get('/api/voice/calls').json()['calls']==[]
    assert c.get('/api/voice/config').json()['enrolled'] is False
    assert c.post('/api/voice/simulate',json={}).status_code==400

def test_unconfigured_provider_returns_503(tmp_path):
    app=create_app({**CONFIG,'VOICE_ENABLED':'false','UPLOAD_DIR':str(tmp_path/'uploads'),'MODEL_DIR':str(tmp_path/'models')})
    with TestClient(app) as c:
        assert c.post('/voice/twilio/incoming').status_code==503
