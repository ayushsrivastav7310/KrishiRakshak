import base64
import hashlib
import hmac
import io
import json
import sqlite3
import time
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.api import create_app
from app.config import Settings
from app.models import Farm

ORIGIN = 'http://127.0.0.1:5173'
CONFIG = {'APP_ENV': 'test', 'DEMO_AUTH': 'true', 'DEMO_OTP': '123456',
          'JWT_SECRET': 'test-secret-with-at-least-thirty-two-characters', 'DATABASE_PATH': ':memory:'}
FARM = {'farmerName': 'Asha', 'farmName': 'Green Acres', 'village': 'Rampur',
        'district': 'Lucknow', 'state': 'Uttar Pradesh', 'area': 2.5, 'unit': 'acres',
        'soilType': 'loamy', 'water': 'rainfed', 'sowingMonth': 'June', 'npkUnit': ''}

@pytest.fixture
def api(tmp_path):
    app = create_app({**CONFIG, 'UPLOAD_DIR': str(tmp_path / 'photos')})
    with TestClient(app, headers={'Origin': ORIGIN}) as client:
        yield app, client

def login(client, phone='+919876543210'):
    result = client.post('/api/auth/request-otp', json={'phone': phone})
    assert result.status_code == 200, result.text
    result = client.post('/api/auth/verify-otp', json={'phone': phone, 'otp': '123456'})
    assert result.status_code == 200, result.text
    return result

def image_bytes():
    data = io.BytesIO()
    Image.new('RGB', (4, 4), 'brown').save(data, format='PNG')
    return data.getvalue()

def test_login_cookie_session_farm_edit_and_logout(api):
    app, client = api
    assert client.get('/api/auth/me').status_code == 401
    response = login(client)
    assert response.json()['farm'] is None
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie
    assert client.put('/api/farm', json=FARM).status_code == 200
    assert client.get('/api/auth/me').json()['farm']['farmerName'] == 'Asha'
    edited = {**FARM, 'farmName': 'New name', 'nitrogen': '10', 'npkUnit': 'kg/ha', 'ph': '7'}
    assert client.put('/api/farm', json=edited).status_code == 200
    assert client.get('/api/farm').json()['farm']['farmName'] == 'New name'
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    login(client)
    assert client.get('/api/auth/me').json()['farm']['farmName'] == 'New name'

def test_otp_invalid_expired_attempts_and_reuse(api):
    app, client = api
    phone = '+919876543210'
    assert client.post('/api/auth/request-otp', json={'phone': '123'}).status_code == 400
    assert client.post('/api/auth/request-otp', json={'phone': phone}).status_code == 200
    assert client.post('/api/auth/request-otp', json={'phone': phone}).status_code == 429
    for _ in range(5):
        assert client.post('/api/auth/verify-otp', json={'phone': phone, 'otp': '000000'}).status_code == 400
    assert client.post('/api/auth/verify-otp', json={'phone': phone, 'otp': '123456'}).status_code == 429
    phone = '+919876543211'
    client.post('/api/auth/request-otp', json={'phone': phone})
    with app.state.database.connection:
        app.state.database.connection.execute('UPDATE otp_challenges SET expires=0 WHERE phone=?', (phone,))
    assert client.post('/api/auth/verify-otp', json={'phone': phone, 'otp': '123456'}).status_code == 400
    login(client, '+919876543212')
    assert client.post('/api/auth/verify-otp', json={'phone': '+919876543212', 'otp': '123456'}).status_code == 400
    row = app.state.database.connection.execute('SELECT hash FROM otp_challenges WHERE phone=?', ('+919876543210',)).fetchone()
    assert row['hash'] == hmac.new(CONFIG['JWT_SECRET'].encode(), b'+919876543210:123456', hashlib.sha256).hexdigest()

@pytest.mark.parametrize('changes', [
    {'area': 0}, {'area': True}, {'area': []}, {'ph': 15}, {'ph': -1},
    {'nitrogen': 2}, {'latitude': True}, {'latitude': 27}, {'farmerName': '   '},
    {'village': '', 'district': '', 'state': ''}, {'sowingMonth': ''},
])
def test_server_validation(api, changes):
    app, client = api
    login(client)
    response = client.put('/api/farm', json={**FARM, **changes})
    assert response.status_code == 400
    assert 'fields' in response.json()

def test_optional_soil_values_and_coordinates(api):
    app, client = api
    login(client)
    body = {**FARM, 'village': '', 'district': '', 'state': '', 'latitude': '0', 'longitude': '0',
            'ph': '', 'nitrogen': '', 'phosphorus': '', 'potassium': ''}
    response = client.put('/api/farm', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['farm']['latitude'] == 0
    assert 'ph' not in response.json()['farm']

def test_photos_and_owner_isolation(api):
    app, first = api
    login(first)
    first.put('/api/farm', json=FARM)
    invalid = first.post('/api/farm/soil-photo', files={'photo': ('x.png', b'not an image', 'image/png')})
    assert invalid.status_code == 400
    oversized = first.post('/api/farm/soil-photo', files={'photo': ('x.png', b'x' * (5 * 1024 * 1024 + 1), 'image/png')})
    assert oversized.status_code == 400
    huge = first.post('/api/farm/soil-photo', files={'photo': ('x.png', b'x' * (6 * 1024 * 1024 + 1), 'image/png')})
    assert huge.status_code == 413
    data = image_bytes()
    assert first.post('/api/farm/soil-photo', files={'photo': ('x.jpg', data, 'image/jpeg')}).status_code == 400
    assert first.post('/api/farm/soil-photo', files={'photo': ('../../evil.png', data, 'image/png')}).status_code == 200
    assert first.get('/api/farm/soil-photo').content == data
    original_cookie = first.cookies.get('session')
    # Switch users in the same test client to exercise the exact same API paths.
    login(first, '+919876543211')
    assert first.get('/api/farm').json()['farm'] is None
    assert first.get('/api/farm/soil-photo').status_code == 404
    assert first.delete('/api/farm/soil-photo').status_code == 200
    first.put('/api/farm', json={**FARM, 'farmerName': 'Bala'})
    first.cookies.set('session', original_cookie)
    assert first.get('/api/farm').json()['farm']['farmerName'] == 'Asha'
    assert first.get('/api/farm/soil-photo').status_code == 200
    assert first.post('/api/farm/soil-photo', files={'photo': ('new.png', data, 'image/png')}).status_code == 200
    assert len(list(app.state.settings.upload_dir.iterdir())) == 1
    assert first.delete('/api/farm/soil-photo').status_code == 200
    assert first.get('/api/farm/soil-photo').status_code == 404
    assert not list(app.state.settings.upload_dir.iterdir())

def test_csrf_rate_limits_forged_cookie_and_body_limits(api):
    app, client = api
    assert client.post('/api/auth/logout', headers={'Origin': 'https://evil.test'}).status_code == 403
    assert client.post('/api/auth/logout', headers={'Origin': ''}).status_code == 403
    client.cookies.set('session', 'forged')
    assert client.get('/api/auth/me').status_code == 401
    for _ in range(15):
        client.post('/api/auth/request-otp', json={'phone': 'bad'})
    assert client.post('/api/auth/request-otp', json={'phone': '+919876543210'}).status_code == 429
    assert client.put('/api/farm', content=b'x' * 40000, headers={'Content-Type': 'application/json'}).status_code == 413
    for _ in range(40):
        client.post('/api/auth/verify-otp', json={'phone': '+919876543210', 'otp': '000000'})
    assert client.post('/api/auth/verify-otp', json={'phone': '+919876543210', 'otp': '000000'}).status_code == 429
    assert client.get('/api/config').headers['cache-control'] == 'no-store'
    assert client.get('/api/nonexistent').status_code == 404

def test_production_demo_guard_missing_provider_and_secure_cookie(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='forbidden'):
        Settings.load({**CONFIG, 'APP_ENV': 'production'})
    with pytest.raises(ValueError, match='forbidden'):
        Settings.load({**CONFIG, 'NODE_ENV': 'production'})
    with pytest.raises(ValueError, match='JWT_SECRET'):
        Settings.load({**CONFIG, 'JWT_SECRET': 'short'})
    app = create_app({**CONFIG, 'APP_ENV': 'production', 'DEMO_AUTH': 'false', 'UPLOAD_DIR': str(tmp_path)})
    with TestClient(app, base_url='https://testserver', headers={'Origin': ORIGIN}) as client:
        assert client.post('/api/auth/request-otp', json={'phone': '+919876543210'}).status_code == 503
        now = int(time.time() * 1000)
        digest = hmac.new(CONFIG['JWT_SECRET'].encode(), b'+919876543210:123456', hashlib.sha256).hexdigest()
        with app.state.database.connection:
            app.state.database.connection.execute('INSERT INTO otp_challenges VALUES(?,?,?,?,?)', ('+919876543210', digest, now + 300000, now, 0))
        result = client.post('/api/auth/verify-otp', json={'phone': '+919876543210', 'otp': '123456'})
        assert result.status_code == 503  # A local digest cannot bypass the real provider.
        from app.otp import OTPService
        async def approved(*args):
            return True
        monkeypatch.setattr(OTPService, 'check', approved)
        result = client.post('/api/auth/verify-otp', json={'phone': '+919876543210', 'otp': '123456'})
        assert 'Secure' in result.headers['set-cookie']

def test_existing_sqlite_schema_and_jwt_survive_migration(tmp_path):
    filename = tmp_path / 'old.sqlite'
    # Same tables, camelCase JSON and JWT claims as the original Express backend.
    conn = sqlite3.connect(filename)
    conn.executescript('CREATE TABLE users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE NOT NULL); CREATE TABLE farms (user_id INTEGER PRIMARY KEY, data TEXT NOT NULL, photo TEXT);')
    conn.execute('INSERT INTO users VALUES(?,?)', (7, '+919876543210'))
    conn.execute('INSERT INTO farms VALUES(?,?,NULL)', (7, json.dumps(FARM)))
    conn.commit()
    conn.close()
    token = jwt.encode({'sub': '7', 'iat': int(time.time()), 'exp': int(time.time()) + 600,
                        'iss': 'krishi-rakshak', 'aud': 'farmer'}, CONFIG['JWT_SECRET'], algorithm='HS256')
    for _ in range(2):
        app = create_app({**CONFIG, 'DATABASE_PATH': str(filename), 'UPLOAD_DIR': str(tmp_path / 'photos')})
        with TestClient(app, headers={'Origin': ORIGIN}) as client:
            client.cookies.set('session', token)
            result = client.get('/api/auth/me')
            assert result.status_code == 200
            assert result.json()['farm']['farmerName'] == 'Asha'
            assert client.put('/api/farm', json={**FARM, 'farmName': 'After migration'}).status_code == 200
    assert result.json()['farm']['farmName'] == 'After migration'

def test_api_docs_and_frontend_build(api):
    app, client = api
    assert client.get('/docs').status_code == 200
    schema = client.get('/openapi.json').json()
    assert '/api/auth/request-otp' in schema['paths']
    if app.state.settings.frontend_dist.is_dir():
        response = client.get('/')
        assert response.status_code == 200
        assert 'KrishiRakshak' in response.text



