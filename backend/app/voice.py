"""Hindi IVR adapter. Provider speech/TTS, deterministic intent routing, existing services.

Webhooks are outside /api so browser CSRF remains unchanged. Each webhook instead
requires a Twilio signature over the configured public URL and all form values.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Annotated
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.intelligence import CropInput, FEATURES
from app.irrigation import IrrigationInput, irrigation_weather, calculate
from app.mandi import prices

MENU = 'फसल सलाह के लिए 1, सिंचाई के लिए 2, मंडी भाव के लिए 3 दबाएं या अपना सवाल बोलें। फिर सुनने के लिए 9, समाप्त करने के लिए 0 दबाएं।'
PIN_PROMPT = 'कृषि रक्षक में स्वागत है। बातचीत का लिखित विवरण आपके खाते में सहेजा जाएगा। सहमति हो तो अपना छह अंकों का हेल्पलाइन पिन दबाएं। नहीं तो कॉल बंद करें।'
PROMPTS = dict(zip(FEATURES, [
    'नाइट्रोजन का मान बताएं। मॉडल डेटासेट की इकाई में मान चाहिए।',
    'फास्फोरस का मान बताएं। मॉडल डेटासेट की इकाई में मान चाहिए।',
    'पोटैशियम का मान बताएं। मॉडल डेटासेट की इकाई में मान चाहिए।',
    'तापमान डिग्री सेल्सियस में बताएं।', 'नमी प्रतिशत में बताएं।',
    'मिट्टी का पी एच बताएं।', 'वर्षा मिलीमीटर में बताएं। डेटासेट की वर्षा अवधि अनिर्दिष्ट है।']))
CROPS = {'1': 'Wheat', '2': 'Rice', '3': 'Maize', '4': 'Tomato'}
CROP_WORDS = {'गेहूं': 'Wheat', 'गेहूँ': 'Wheat', 'धान': 'Rice', 'चावल': 'Rice', 'मक्का': 'Maize', 'टमाटर': 'Tomato', 'wheat': 'Wheat', 'rice': 'Rice', 'maize': 'Maize', 'tomato': 'Tomato'}


class Enrollment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pin: str = Field(pattern=r'^[0-9]{6}$')
    consent: bool
    crop: CropInput | None = None
    irrigation: IrrigationInput | None = None


class Simulation(BaseModel):
    text: str = Field(default='', max_length=500)
    callId: str | None = Field(default=None, max_length=80)


def intent(text):
    text = text.casefold().strip()
    groups = [('crop', ['फसल', 'crop', 'बीज']), ('irrigation', ['सिंचाई', 'पानी', 'irrigat', 'water']), ('mandi', ['मंडी', 'भाव', 'कीमत', 'mandi', 'price', 'market'])]
    if text in {'1', '2', '3'}:
        return {'1': 'crop', '2': 'irrigation', '3': 'mandi'}[text]
    hits = [name for name, words in groups if any(word in text for word in words)]
    return hits[0] if len(hits) == 1 else None


def number(text):
    value = text.translate(str.maketrans('०१२३४५६७८९', '0123456789')).strip().replace(' दशमलव ', '.').replace(' point ', '.')
    # DTMF * is a decimal point. Whole utterances only: never silently extract
    # a plausible number from a sentence containing conflicting measurements.
    value = value.replace('*', '.')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
        raise ValueError('numeric input required')
    return float(value)


def pin_hash(pin, salt):
    return hashlib.scrypt(pin.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def india_today():
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()


def valid_signature(url, form, token, signature):
    material = url
    for key in sorted(form):
        for value in sorted(set(form.getlist(key))):
            material += key + value
    expected = base64.b64encode(hmac.new(token.encode(), material.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(expected, signature)


def twiml(message, action='', pin=False, numeric=False, end=False):
    root = Element('Response')
    parent = root
    if not end:
        attrs = {'input': 'dtmf' if pin else 'speech dtmf', 'action': action,
                 'method': 'POST', 'language': 'hi-IN', 'timeout': '7',
                 'speechTimeout': 'auto', 'actionOnEmptyResult': 'true'}
        if pin:
            attrs['numDigits'] = '6'
        elif not numeric:
            attrs['numDigits'] = '1'
        parent = SubElement(root, 'Gather', attrs)
    SubElement(parent, 'Say', {'language': 'hi-IN', 'voice': 'Polly.Aditi'}).text = message
    if end:
        SubElement(root, 'Hangup')
    return tostring(root, encoding='unicode')


def voice_router(db, current_user, registry, settings):
    router = APIRouter(tags=['Voice helpline'])
    User = Annotated[dict, Depends(current_user)]
    with db.lock, db.connection:
        db.connection.executescript('''
        CREATE TABLE IF NOT EXISTS voice_profiles (
          user_id INTEGER PRIMARY KEY REFERENCES users(id), salt TEXT NOT NULL,
          pin_hash TEXT NOT NULL, data TEXT NOT NULL, failures INTEGER NOT NULL DEFAULT 0,
          locked_until REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS voice_calls (
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          mode TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
          updated REAL NOT NULL, state TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS voice_owner ON voice_calls(user_id, created DESC);
        ''')

    def configured():
        parsed = urlsplit(settings.voice_public_url)
        return bool(settings.voice_enabled and parsed.scheme == 'https' and parsed.netloc
                    and not parsed.query and not parsed.fragment and parsed.path in ('', '/')
                    and settings.voice_account_sid and settings.voice_auth_token and settings.voice_phone)

    def profile(uid):
        return db.connection.execute('SELECT * FROM voice_profiles WHERE user_id=?', (uid,)).fetchone()

    def load(cid):
        row = db.connection.execute('SELECT * FROM voice_calls WHERE id=?', (cid,)).fetchone()
        return ({**dict(row), 'state': json.loads(row['state'])} if row else None)

    def save(call):
        db.connection.execute('INSERT INTO voice_calls VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,updated=excluded.updated,state=excluded.state',
                              (call['id'], call['user_id'], call['mode'], call['status'], call['created'], time.time(), json.dumps(call['state'], ensure_ascii=False)))

    def new_call(cid, uid, mode, authenticated=False):
        now = time.time()
        return dict(id=cid, user_id=uid, mode=mode, status='active', created=now, updated=now,
                    state=dict(authenticated=authenticated, step=0, phase='menu', retries=0, values={}, turns=[], cache={}, last=MENU))

    def public(call):
        state = call['state']
        return {'id': call['id'], 'mode': call['mode'], 'status': call['status'],
                'createdAt': call['created'], 'updatedAt': call['updated'],
                'turns': state['turns'], 'message': state['last'], 'intent': state.get('intent')}

    @router.get('/api/voice/config')
    def config(user: User):
        with db.lock:
            p = profile(user['id'])
        return {'provider': 'twilio', 'configured': configured(), 'liveVerified': False,
                'phone': settings.voice_phone if configured() else None, 'enrolled': bool(p),
                'crop': json.loads(p['data']).get('crop') if p else None,
                'irrigation': json.loads(p['data']).get('irrigation') if p else None}

    @router.put('/api/voice/profile')
    async def enroll(body: Enrollment, user: User):
        if not body.consent:
            raise HTTPException(400, 'Consent is required to store call transcripts.')
        salt = secrets.token_hex(16)
        digest = await run_in_threadpool(pin_hash, body.pin, salt)
        data = body.model_dump(mode='json', exclude={'pin', 'consent'})
        data['irrigationUpdatedDate'] = india_today()
        with db.lock, db.connection:
            db.connection.execute('INSERT INTO voice_profiles VALUES(?,?,?,?,0,0) ON CONFLICT(user_id) DO UPDATE SET salt=excluded.salt,pin_hash=excluded.pin_hash,data=excluded.data,failures=0,locked_until=0',
                                  (user['id'], salt, digest, json.dumps(data)))
            # PIN rotation revokes all active calls as well.
            db.connection.execute("UPDATE voice_calls SET status='revoked' WHERE user_id=? AND status='active'", (user['id'],))
        return {'enrolled': True}

    @router.delete('/api/voice/profile')
    def disable(user: User):
        with db.lock, db.connection:
            db.connection.execute('DELETE FROM voice_profiles WHERE user_id=?', (user['id'],))
            db.connection.execute('DELETE FROM voice_calls WHERE user_id=?', (user['id'],))
        return {'enrolled': False}

    @router.get('/api/voice/calls')
    def calls(user: User):
        with db.lock:
            ids = db.connection.execute('SELECT id FROM voice_calls WHERE user_id=? ORDER BY created DESC LIMIT 30', (user['id'],)).fetchall()
            return {'calls': [public(load(row['id'])) for row in ids]}

    def answer(call, text):
        """Runs in a worker thread; serialize the state machine per SQLite transaction.

        Irrigation uses preconfigured measurements and cached weather results below;
        outbound weather is fetched before entering this transaction.
        """
        s = call['state']
        p = profile(call['user_id'])
        data = json.loads(p['data']) if p else {}
        if text == '0' and s['phase'] == 'menu':
            call['status'] = 'completed'
            return 'धन्यवाद। नमस्ते।'
        if text == '9' and s['phase'] != 'crop-values':
            return s['last']
        if s['phase'] == 'crop-values':
            key = FEATURES[len(s['values'])]
            try:
                value = number(text)
                # Validate this field using the same model contract as the API.
                from pydantic import TypeAdapter
                from typing import Annotated as A
                field = CropInput.model_fields[key]
                TypeAdapter(A[field.annotation, *field.metadata]).validate_python(value)
            except (ValueError, ValidationError):
                s['retries'] += 1
                return 'मान समझ नहीं आया। अंक बोलें या कीपैड से डालकर हैश दबाएं। दशमलव के लिए स्टार दबाएं। ' + PROMPTS[key]
            s['values'][key] = value
            s['retries'] = 0
            if len(s['values']) < len(FEATURES):
                return PROMPTS[FEATURES[len(s['values'])]]
            s['phase'] = 'menu'
            data['crop'] = s['values']
        elif s['phase'] == 'mandi-crop':
            commodity = CROPS.get(text) or next((v for k, v in CROP_WORDS.items() if k in text.casefold()), None)
            if not commodity:
                s['retries'] += 1
                return 'गेहूं के लिए 1, चावल 2, मक्का 3, टमाटर 4 दबाएं या नाम बोलें।'
            s['phase'] = 'menu'
            farm = db.farm_for(call['user_id']) or {}
            if not farm.get('state') or not farm.get('district'):
                return 'पहले डैशबोर्ड पर अपने खेत का राज्य और जिला सहेजें। ' + MENU
            result = prices(db, state=farm['state'], district=farm['district'], commodity=commodity, limit=1)
            if not result['records']:
                return 'आपके जिले में इस फसल का आधिकारिक मंडी रिकॉर्ड उपलब्ध नहीं है। ' + MENU
            r = result['records'][0]
            return f"{r['market']} मंडी में {commodity}, किस्म {r['variety']}, तारीख {r['date']}, सरकारी दर्ज भाव {r['modal']} रुपये प्रति क्विंटल। " + ('यह पुराना रिकॉर्ड है। ' if r['stale'] else '') + 'यह खरीद की गारंटी नहीं है। ' + MENU
        else:
            selected = intent(text)
            if not selected:
                s['retries'] += 1
                return 'सवाल समझ नहीं आया। ' + MENU
            s['intent'] = selected
            s['retries'] = 0
            if selected == 'mandi':
                s['phase'] = 'mandi-crop'
                return 'गेहूं के लिए 1, चावल 2, मक्का 3, टमाटर 4 दबाएं या नाम बोलें।'
            if selected == 'crop' and not data.get('crop'):
                s['phase'] = 'crop-values'
                s['values'] = {}
                return 'सात माप चाहिए। मिट्टी जांच की इकाइयों को मॉडल की इकाइयों से मिलाएं। अज्ञात मान का अनुमान न लगाएं। ' + PROMPTS['N']
        try:
            if s['intent'] == 'crop':
                result = registry.crop(CropInput(**data['crop']))
                return f"मॉडल का सुझाव {result['recommendedCrop']} है। यह उपज की गारंटी नहीं है। स्थानीय मौसम, पानी और कृषि विशेषज्ञ से पुष्टि करें। " + MENU
            if not data.get('irrigation'):
                return 'सिंचाई के लिए डैशबोर्ड पर फसल, बुवाई तारीख, क्षेत्रफल, स्थान और मिट्टी के जल माप सहेजें। बिना माप पानी की मात्रा नहीं बताई जाएगी। ' + MENU
            if data.get('irrigationUpdatedDate') != india_today():
                return 'आज के मिट्टी जल माप डैशबोर्ड पर अपडेट करें। पुराने माप से पानी की मात्रा नहीं बताई जाएगी। ' + MENU
            body = IrrigationInput(**data['irrigation'])
            weather = s.pop('_weather', None)
            if weather is None:
                return 'मौसम सेवा अभी उपलब्ध नहीं है। बाद में प्रयास करें। ' + MENU
            result = calculate(body, weather)
            if result['depthMm'] is None:
                return 'पानी की सही मात्रा के लिए वर्तमान जड़ क्षेत्र की नमी और जल धारण माप चाहिए। कृषि विशेषज्ञ से संपर्क करें। ' + MENU
            return f"अनुमानित सिंचाई {result['depthMm']} मिलीमीटर, कुल {result['volumeLiters']} लीटर। " + (f"सुझाई तारीख {result['suggestedDate']}। " if result['suggestedDate'] else 'अगले सात दिन सिंचाई का संकेत नहीं है। ') + 'यह मौसम और सरल जल संतुलन पर आधारित अनुमान है। ' + MENU
        except (HTTPException, ValidationError, KeyError, ValueError):
            return 'सहेजे गए माप या मॉडल अभी उपलब्ध नहीं हैं। डैशबोर्ड पर जांचें या कृषि विशेषज्ञ से संपर्क करें। ' + MENU

    async def process(cid, uid, text, step=None, confidence=None):
        # Slow external work does not hold the DB lock. CAS below rejects stale steps.
        weather = None
        with db.lock:
            call = load(cid)
            p = profile(uid)
            data = json.loads(p['data']) if p else {}
            should_weather = (call and call['status'] == 'active' and intent(text) == 'irrigation'
                              and call['state']['phase'] == 'menu' and data.get('irrigation'))
        if should_weather:
            try:
                body = IrrigationInput(**data['irrigation'])
                weather = await irrigation_weather(body.latitude, body.longitude)
            except (HTTPException, ValidationError):
                pass
        def commit():
            with db.lock, db.connection:
                call = load(cid)
                if not call or call['user_id'] != uid:
                    raise HTTPException(404, 'Call not found.')
                s = call['state']
                if call['status'] != 'active' or time.time() - call['created'] > 900:
                    call['status'] = 'completed' if call['status'] == 'active' else call['status']
                    save(call)
                    return call, twiml('कॉल समाप्त हो गई।', end=True)
                if step is not None and str(step) in s['cache']:
                    return call, s['cache'][str(step)]
                if step is not None and step != s['step']:
                    raise HTTPException(409, 'Stale call step.')
                if not s['authenticated']:
                    p = profile(uid)
                    if not p or p['locked_until'] > time.time():
                        call['status'] = 'blocked'
                        message = 'हेल्पलाइन उपलब्ध नहीं है। बाद में प्रयास करें।'
                    elif hmac.compare_digest(pin_hash(text, p['salt']), p['pin_hash']):
                        s['authenticated'] = True
                        db.connection.execute('UPDATE voice_profiles SET failures=0 WHERE user_id=?', (uid,))
                        message = MENU
                    else:
                        failures = p['failures'] + 1
                        db.connection.execute('UPDATE voice_profiles SET failures=?,locked_until=? WHERE user_id=?', (failures, time.time()+900 if failures >= 5 else 0, uid))
                        s['retries'] += 1
                        message = 'पिन गलत है। अपना छह अंकों का पिन दबाएं।'
                    # Never persist PINs in transcripts, cache keys or events.
                else:
                    try:
                        low = confidence is not None and float(confidence) < .45
                    except ValueError:
                        low = True
                    if low:
                        s['retries'] += 1
                        message = 'आवाज स्पष्ट नहीं थी। फिर बोलें या कीपैड दबाएं। ' + s['last']
                    else:
                        if weather is not None:
                            s['_weather'] = weather
                        message = answer(call, text)
                        s.pop('_weather', None)
                    s['turns'].append({'input': text, 'reply': message, 'at': time.time()})
                s['step'] += 1
                if s['step'] >= 20 or s['retries'] >= 3:
                    call['status'] = 'completed'
                    message = 'अभी सहायता पूरी नहीं हो सकी। बाद में प्रयास करें या कृषि विशेषज्ञ से संपर्क करें।'
                s['last'] = message
                action = settings.voice_public_url + '/voice/twilio/input?step=' + str(s['step'])
                xml = twiml(message, action, pin=not s['authenticated'], numeric=s['phase']=='crop-values', end=call['status']!='active')
                if step is not None:
                    s['cache'][str(step)] = xml
                save(call)
                return call, xml
        return await run_in_threadpool(commit)

    @router.post('/api/voice/simulate')
    async def simulate(body: Simulation, user: User):
        with db.lock, db.connection:
            if not profile(user['id']):
                raise HTTPException(400, 'Enable helpline and consent before simulation.')
            if not body.callId:
                call = new_call('sim-' + secrets.token_hex(16), user['id'], 'simulation', True)
                save(call)
                return public(call)
            call = load(body.callId)
            if not call or call['user_id'] != user['id'] or call['mode'] != 'simulation':
                raise HTTPException(404, 'Simulation not found.')
        call, _ = await process(body.callId, user['id'], body.text.strip())
        return public(call)

    async def verified(request):
        if not configured():
            raise HTTPException(503, 'Voice provider is not configured.')
        if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            raise HTTPException(415, 'Form body required.')
        # Unlike /api routes, provider webhooks have no browser Origin. Bound their body.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                raise HTTPException(413, 'Webhook too large.')
        from starlette.datastructures import FormData
        from urllib.parse import parse_qsl
        form = FormData(parse_qsl(body.decode('utf-8', errors='replace'), keep_blank_values=True))
        url = settings.voice_public_url + request.url.path
        if request.url.query:
            url += '?' + request.url.query
        if not valid_signature(url, form, settings.voice_auth_token, request.headers.get('x-twilio-signature', '')):
            raise HTTPException(403, 'Invalid provider signature.')
        if form.get('AccountSid') != settings.voice_account_sid or form.get('To') != settings.voice_phone:
            raise HTTPException(403, 'Unexpected provider account or destination.')
        if not re.fullmatch(r'CA[0-9a-fA-F]{32}', form.get('CallSid', '')):
            raise HTTPException(400, 'Invalid call identifier.')
        if any(len(v) > 1000 for _, v in form.multi_items()):
            raise HTTPException(400, 'Invalid provider field.')
        return form

    def xml_response(xml):
        return Response(xml, media_type='application/xml', headers={'Cache-Control': 'no-store'})

    @router.post('/voice/twilio/incoming')
    async def incoming(request: Request):
        f = await verified(request)
        with db.lock, db.connection:
            user = db.connection.execute('SELECT id FROM users WHERE phone=?', (f.get('From'),)).fetchone()
            if not user or not profile(user['id']):
                return xml_response(twiml('हेल्पलाइन के लिए पहले अपना खाता और पिन डैशबोर्ड पर बनाएं।', end=True))
            call = load(f['CallSid'])
            if not call:
                recent = db.connection.execute("SELECT count(*) FROM voice_calls WHERE user_id=? AND mode='twilio' AND created>?", (user['id'], time.time()-900)).fetchone()[0]
                if recent >= 10:
                    return xml_response(twiml('कृपया पंद्रह मिनट बाद प्रयास करें।', end=True))
                call = new_call(f['CallSid'], user['id'], 'twilio')
                save(call)
            # Initial URL replay must not reset PIN attempts or an existing call.
            if call['user_id'] != user['id'] or call['state']['step'] or call['status'] != 'active':
                return xml_response(twiml('कॉल समाप्त हो गई। फिर कॉल करें।', end=True))
        return xml_response(twiml(PIN_PROMPT, settings.voice_public_url + '/voice/twilio/input?step=0', pin=True))

    @router.post('/voice/twilio/input')
    async def input_webhook(request: Request, step: int):
        f = await verified(request)
        with db.lock:
            call = load(f['CallSid'])
            user = db.connection.execute('SELECT id FROM users WHERE phone=?', (f.get('From'),)).fetchone()
            if not call or not user or user['id'] != call['user_id'] or call['mode'] != 'twilio':
                raise HTTPException(404, 'Call not found.')
        _, xml = await process(call['id'], call['user_id'], (f.get('Digits') or f.get('SpeechResult') or '').strip()[:500], step,
                               f.get('Confidence') if not f.get('Digits') else None)
        return xml_response(xml)

    @router.post('/voice/twilio/status')
    async def status(request: Request):
        f = await verified(request)
        with db.lock, db.connection:
            call = load(f['CallSid'])
            if call and call['mode'] == 'twilio' and call['status'] == 'active' and f.get('CallStatus') in {'completed', 'failed', 'busy', 'no-answer', 'canceled'}:
                call['status'] = f['CallStatus']
                save(call)
        return Response(status_code=204)

    return router
