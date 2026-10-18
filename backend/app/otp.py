"""Demo OTP adapter and hashing. A real SMS provider can implement issue later."""
import hashlib
import hmac
import secrets
import re
import httpx2 as httpx
import phonenumbers
from fastapi import HTTPException
from .config import Settings

def normalize_phone(value: str) -> str:
    try:
        if not value.startswith('+'):
            raise ValueError()
        phone = phonenumbers.parse(value, None)
        if not phonenumbers.is_valid_number(phone):
            raise ValueError()
        return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164)
    except (ValueError, phonenumbers.NumberParseException):
        raise HTTPException(400, 'Enter a valid phone number with country code.') from None

class OTPService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def digest(self, phone: str, code: str) -> str:
        return hmac.new(self.settings.secret.encode(), f'{phone}:{code}'.encode(), hashlib.sha256).hexdigest()

    def matches(self, phone: str, code: str, digest: str) -> bool:
        return hmac.compare_digest(self.digest(phone, code), digest)

    async def issue(self, phone: str) -> str:
        if self.settings.demo_auth:
            return self.settings.demo_otp
        result = await self.provider('Verifications', {'To': phone, 'Channel': 'sms'})
        if result.get('status') != 'pending':
            raise HTTPException(503, 'SMS verification could not be started. Please try again.')
        # A random challenge marker is hashed locally; Twilio owns the actual OTP.
        return secrets.token_urlsafe(32)

    async def check(self, phone: str, code: str, digest: str) -> bool:
        if self.settings.demo_auth:
            return self.matches(phone, code, digest)
        result = await self.provider('VerificationCheck', {'To': phone, 'Code': code})
        return result.get('status') == 'approved' and result.get('to') == phone

    async def provider(self, resource, data):
        sid = self.settings.verify_service_sid
        if not re.fullmatch(r'VA[0-9a-fA-F]{32}', sid) or not self.settings.voice_account_sid or not self.settings.voice_auth_token:
            raise HTTPException(503, 'SMS authentication is not configured. Contact the app administrator.')
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(f'https://verify.twilio.com/v2/Services/{sid}/{resource}',
                    data=data, auth=(self.settings.voice_account_sid, self.settings.voice_auth_token))
            if response.status_code == 429:
                raise HTTPException(429, 'Too many verification requests. Please try again later.')
            if resource == 'VerificationCheck' and response.status_code == 404:
                return {'status': 'expired'}
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'SMS verification service is unavailable. Please try again.') from None
