"""Demo OTP adapter and hashing. A real SMS provider can implement issue later."""
import hashlib
import hmac
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
        # Add an SMS provider here. Return only after provider acceptance.
        # Never log phone numbers, OTPs, tokens or provider credentials.
        raise HTTPException(503, 'SMS authentication is not configured. Contact the app administrator.')
