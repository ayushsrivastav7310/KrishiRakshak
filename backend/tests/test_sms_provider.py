import asyncio
from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
from fastapi import HTTPException
from app.config import Settings
from app.otp import OTPService
from test_api import CONFIG


def provider():
    settings = Settings.load({**CONFIG, 'DEMO_AUTH': 'false', 'TWILIO_VERIFY_SERVICE_SID': 'VA' + 'a'*32,
                              'TWILIO_ACCOUNT_SID': 'AC' + 'b'*32, 'TWILIO_AUTH_TOKEN': 'test-only'})
    return OTPService(settings)


def test_otp_is_approved_by_provider_and_bound_to_phone(monkeypatch):
    service = provider()
    request = AsyncMock(side_effect=[{'status': 'pending'}, {'status': 'approved', 'to': '+919876543210'},
                                     {'status': 'approved', 'to': '+919999999999'}, {'status': 'pending'}])
    monkeypatch.setattr(service, 'provider', request)
    marker = asyncio.run(service.issue('+919876543210'))
    assert len(marker) > 20 and not marker.isdigit()
    assert asyncio.run(service.check('+919876543210', '123456', 'ignored'))
    assert not asyncio.run(service.check('+919876543210', '123456', 'ignored'))
    assert not asyncio.run(service.check('+919876543210', '123456', 'ignored'))
    request.assert_any_await('Verifications', {'To': '+919876543210', 'Channel': 'sms'})


@pytest.mark.parametrize('status,expected', [(429,429), (500,503), (401,503)])
def test_provider_errors_are_sanitized(monkeypatch, status, expected):
    response = httpx.Response(status, request=httpx.Request('POST', 'https://verify.twilio.com'),
                              json={'message': 'private provider details'})
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client)
    with pytest.raises(HTTPException) as error:
        asyncio.run(provider().issue('+919876543210'))
    assert error.value.status_code == expected
    assert 'private provider details' not in error.value.detail
