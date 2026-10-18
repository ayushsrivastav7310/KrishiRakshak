"""Run from backend/: python -m uvicorn main:app --reload."""
import io
import json
import secrets
import time
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.database import Database
from app.models import Farm, PhoneRequest, VerifyRequest
from app.otp import OTPService, normalize_phone
from app.security import SecurityMiddleware
from app.intelligence import get_registry
from app.intelligence_api import intelligence_router
from app.phases_api import phases_router
from app.voice import voice_router


def create_app(overrides: dict | None = None) -> FastAPI:
    settings = Settings.load(overrides)
    database = Database(settings.database_path)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    otp_service = OTPService(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        database.close()

    app = FastAPI(title='KrishiRakshak API', version='1.0.0', lifespan=lifespan)
    app.state.database = database
    app.state.settings = settings
    registry = get_registry(str((overrides or {}).get('MODEL_DIR', Path(__file__).resolve().parents[1] / 'artifacts')))
    app.state.models = registry
    app.add_middleware(SecurityMiddleware, origin=settings.origin)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        return JSONResponse({'error': str(error.detail)}, status_code=error.status_code, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, error):
        fields = {}
        for issue in error.errors():
            field = '.'.join(str(part) for part in issue['loc'] if part != 'body') or 'form'
            fields.setdefault(field, []).append(issue['msg'].removeprefix('Value error, '))
        return JSONResponse({'error': 'Please check your details.', 'fields': fields}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        return JSONResponse({'error': 'Something went wrong. Please try again.'}, status_code=500)

    def current_user(request: Request) -> dict:
        try:
            payload = jwt.decode(request.cookies.get('session', ''), settings.secret,
                                 algorithms=['HS256'], issuer='krishi-rakshak', audience='farmer',
                                 options={'require': ['exp', 'sub', 'iss', 'aud']})
            with database.lock:
                user = database.connection.execute('SELECT * FROM users WHERE id=?', (payload['sub'],)).fetchone()
            if not user:
                raise ValueError()
            return dict(user)
        except (jwt.PyJWTError, ValueError, TypeError):
            raise HTTPException(401, 'Please sign in to continue.') from None

    User = Annotated[dict, Depends(current_user)]

    @app.get('/api/config')
    async def config():
        return {'demoAuth': settings.demo_auth}

    @app.post('/api/auth/request-otp')
    async def request_otp(body: PhoneRequest):
        phone = normalize_phone(body.phone)
        now = int(time.time() * 1000)
        with database.lock:
            previous = database.connection.execute('SELECT * FROM otp_challenges WHERE phone=?', (phone,)).fetchone()
            if previous and now - previous['requested'] < 60000:
                raise HTTPException(429, 'Wait 60 seconds before requesting another code.', headers={'Retry-After': '60'})
        code = await otp_service.issue(phone)
        with database.lock, database.connection:
            # Recheck after a provider await so simultaneous requests cannot bypass cooldown.
            previous = database.connection.execute('SELECT requested FROM otp_challenges WHERE phone=?', (phone,)).fetchone()
            if previous and now - previous['requested'] < 60000:
                raise HTTPException(429, 'Wait 60 seconds before requesting another code.')
            database.connection.execute('INSERT OR REPLACE INTO otp_challenges(phone,hash,expires,requested,attempts) VALUES(?,?,?,?,0)',
                                        (phone, otp_service.digest(phone, code), now + 300000, now))
        return {'phone': phone, 'expiresIn': 300, 'resendAfter': 60, 'demoAuth': settings.demo_auth,
                'message': 'Demo authentication: enter the configured demo code. No SMS was sent.' if settings.demo_auth else 'Verification code sent.'}

    @app.post('/api/auth/verify-otp')
    async def verify_otp(body: VerifyRequest, response: Response):
        phone = normalize_phone(body.phone)
        with database.lock:
            row = database.connection.execute('SELECT * FROM otp_challenges WHERE phone=?', (phone,)).fetchone()
            if not row or row['expires'] <= int(time.time() * 1000):
                raise HTTPException(400, 'Code expired. Request a new code.')
            if row['attempts'] >= 5:
                raise HTTPException(429, 'Attempt limit reached. Request a new code after the cooldown.')
            database.connection.execute('UPDATE otp_challenges SET attempts=attempts+1 WHERE phone=?', (phone,))
            database.connection.commit()
            if not otp_service.matches(phone, body.otp, row['hash']):
                raise HTTPException(400, 'Incorrect code. Please try again.')
            with database.connection:
                database.connection.execute('DELETE FROM otp_challenges WHERE phone=?', (phone,))
                database.connection.execute('INSERT OR IGNORE INTO users(phone) VALUES(?)', (phone,))
                user = dict(database.connection.execute('SELECT * FROM users WHERE phone=?', (phone,)).fetchone())
        now = int(time.time())
        token = jwt.encode({'sub': str(user['id']), 'iat': now, 'exp': now + 604800,
                            'iss': 'krishi-rakshak', 'aud': 'farmer'}, settings.secret, algorithm='HS256')
        response.set_cookie('session', token, max_age=604800, httponly=True,
                            secure=settings.production, samesite='strict', path='/')
        return {'user': user, 'farm': database.farm_for(user['id'])}

    @app.get('/api/auth/me')
    async def me(user: User):
        return {'user': user, 'farm': database.farm_for(user['id'])}

    @app.post('/api/auth/logout')
    async def logout(response: Response):
        response.delete_cookie('session', httponly=True, secure=settings.production, samesite='strict', path='/')
        return {'ok': True}

    @app.get('/api/farm')
    async def get_farm(user: User):
        return {'farm': database.farm_for(user['id'])}

    @app.put('/api/farm')
    async def save_farm(body: Farm, user: User):
        with database.lock, database.connection:
            database.connection.execute('INSERT INTO farms(user_id,data) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data',
                                        (user['id'], json.dumps(body.model_dump(exclude_none=True), ensure_ascii=False)))
        return {'farm': database.farm_for(user['id'])}

    def photo_path(filename: str) -> Path:
        candidate = (settings.upload_dir / filename).resolve()
        if candidate.parent != settings.upload_dir:
            raise HTTPException(404, 'Photo not found.')
        return candidate

    @app.post('/api/farm/soil-photo')
    async def upload_photo(user: User, photo: UploadFile = File(...)):
        with database.lock:
            row = database.connection.execute('SELECT * FROM farms WHERE user_id=?', (user['id'],)).fetchone()
        if not row:
            raise HTTPException(400, 'Save your farm before uploading a photo.')
        try:
            data = await photo.read(5 * 1024 * 1024 + 1)
        finally:
            await photo.close()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(400, 'Choose an image up to 5 MB.')
        formats = {'JPEG': ('jpg', 'image/jpeg'), 'PNG': ('png', 'image/png'), 'WEBP': ('webp', 'image/webp')}
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    extension, mime = formats.get(image.format, (None, None))
                    if not extension or mime != photo.content_type:
                        raise ValueError()
                    image.verify()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(400, 'Choose a valid JPEG, PNG or WebP image matching its file type.') from None
        filename = secrets.token_hex(24) + '.' + extension
        destination = photo_path(filename)
        destination.write_bytes(data)
        try:
            with database.lock, database.connection:
                database.connection.execute('UPDATE farms SET photo=? WHERE user_id=?', (filename, user['id']))
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        if row['photo']:
            photo_path(row['photo']).unlink(missing_ok=True)
        return {'ok': True}

    @app.get('/api/farm/soil-photo')
    async def get_photo(user: User):
        with database.lock:
            row = database.connection.execute('SELECT photo FROM farms WHERE user_id=?', (user['id'],)).fetchone()
        if not row or not row['photo'] or not photo_path(row['photo']).is_file():
            raise HTTPException(404, 'No soil photo saved.')
        return FileResponse(photo_path(row['photo']))

    @app.delete('/api/farm/soil-photo')
    async def delete_photo(user: User):
        with database.lock, database.connection:
            row = database.connection.execute('SELECT photo FROM farms WHERE user_id=?', (user['id'],)).fetchone()
            database.connection.execute('UPDATE farms SET photo=NULL WHERE user_id=?', (user['id'],))
        if row and row['photo']:
            photo_path(row['photo']).unlink(missing_ok=True)
        return {'ok': True}

    app.include_router(intelligence_router(database, current_user, registry))
    app.include_router(phases_router(database, current_user, registry.directory, settings.data_gov_api_key))
    app.include_router(voice_router(database, current_user, registry, settings))

    @app.api_route('/api/{rest:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'], include_in_schema=False)
    async def missing_api(rest: str):
        raise HTTPException(404, 'API route not found.')

    if settings.frontend_dist.is_dir():
        app.mount('/', StaticFiles(directory=settings.frontend_dist, html=True), name='frontend')
    return app




