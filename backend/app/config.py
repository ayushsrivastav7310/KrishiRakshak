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
        return cls(environment, secret, demo, code,
                   env.get('APP_ORIGIN', 'http://127.0.0.1:5173'),
                   database if database == ':memory:' else str((BACKEND_ROOT / database).resolve()),
                   (BACKEND_ROOT / env.get('UPLOAD_DIR', './data/uploads')).resolve(),
                   (BACKEND_ROOT.parent / 'frontend/dist').resolve())

