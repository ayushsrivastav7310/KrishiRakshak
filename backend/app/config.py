"""Environment configuration; paths stay relative to the backend folder."""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import dotenv_values

BACKEND_ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Settings:
    environment: str
    secret: str
    demo_auth: bool
    demo_otp: str
    origin: str
    database_path: str
    upload_dir: Path
    frontend_dist: Path
    data_gov_api_key: str = ''
    voice_enabled: bool = False
    voice_public_url: str = ''
    voice_account_sid: str = ''
    voice_auth_token: str = ''
    voice_phone: str = ''
    turso_url: str = ''
    turso_token: str = ''
    photo_storage: str = 'local'
    verify_service_sid: str = ''

    @property
    def production(self) -> bool:
        return self.environment == 'production'

    @classmethod
    def load(cls, overrides: dict | None = None):
        env = {**dotenv_values(BACKEND_ROOT / '.env'), **os.environ, **(overrides or {})}
        environment = 'production' if 'production' in (env.get('APP_ENV'), env.get('NODE_ENV')) else env.get('APP_ENV', env.get('NODE_ENV', 'development'))
        demo = env.get('DEMO_AUTH', 'false') == 'true'
        secret = env.get('JWT_SECRET', '')
        code = env.get('DEMO_OTP', '')
        if environment == 'production' and demo:
            raise ValueError('Demo authentication is forbidden in production.')
        if not secret or len(secret) < 32:
            raise ValueError('Set JWT_SECRET to at least 32 random characters.')
        if demo and not re.fullmatch(r'[0-9]{6}', code):
            raise ValueError('Set a six-digit DEMO_OTP.')
        database = env.get('DATABASE_PATH', './data/krishi.sqlite')
        turso_url = env.get('TURSO_DATABASE_URL', '') or ''
        turso_token = env.get('TURSO_AUTH_TOKEN', '') or ''
        photo_storage = env.get('PHOTO_STORAGE', 'local')
        if bool(turso_url) != bool(turso_token):
            raise ValueError('Set both TURSO_DATABASE_URL and TURSO_AUTH_TOKEN.')
        if photo_storage not in ('local', 'vercel-blob'):
            raise ValueError('PHOTO_STORAGE must be local or vercel-blob.')
        if env.get('VERCEL') == '1' and (not turso_url or photo_storage != 'vercel-blob'):
            raise ValueError('Vercel requires Turso database credentials and PHOTO_STORAGE=vercel-blob; local storage is not durable.')
        return cls(environment, secret, demo, code,
                   env.get('APP_ORIGIN', 'http://127.0.0.1:5173'),
                   database if database == ':memory:' else str((BACKEND_ROOT / database).resolve()),
                   (BACKEND_ROOT / env.get('UPLOAD_DIR', './data/uploads')).resolve(),
                   (BACKEND_ROOT.parent / 'frontend/dist').resolve(),
                   env.get('DATA_GOV_API_KEY', '') or '',
                   env.get('VOICE_ENABLED', 'false') == 'true',
                   (env.get('VOICE_PUBLIC_URL', '') or '').rstrip('/'),
                   env.get('TWILIO_ACCOUNT_SID', '') or '',
                   env.get('TWILIO_AUTH_TOKEN', '') or '',
                   env.get('TWILIO_PHONE_NUMBER', '') or '',
                   turso_url, turso_token, photo_storage,
                   env.get('TWILIO_VERIFY_SERVICE_SID', '') or '')

