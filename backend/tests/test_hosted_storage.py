import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from app.config import Settings
from app.database import Database
from app.photos import Photos
from test_api import CONFIG


def test_vercel_refuses_ephemeral_storage():
    with pytest.raises(ValueError, match='Vercel requires Turso'):
        Settings.load({**CONFIG, 'VERCEL': '1', 'TURSO_DATABASE_URL': '', 'TURSO_AUTH_TOKEN': ''})


def test_cloud_configuration():
    s = Settings.load({**CONFIG, 'VERCEL': '1', 'TURSO_DATABASE_URL': 'turso://database.turso.io',
                       'TURSO_AUTH_TOKEN': 'test-only', 'PHOTO_STORAGE': 'vercel-blob'})
    assert s.photo_storage == 'vercel-blob'
    assert s.turso_url.startswith('turso://')


def test_local_photo_roundtrip_and_traversal(tmp_path):
    photos = Photos(SimpleNamespace(photo_storage='local', upload_dir=tmp_path))
    filename = 'a' * 48 + '.png'
    asyncio.run(photos.put(7, filename, b'photo', 'image/png'))
    assert asyncio.run(photos.get(7, filename)) == (b'photo', 'image/png')
    with pytest.raises(HTTPException):
        asyncio.run(photos.get(7, '../secret.env'))
    asyncio.run(photos.delete(7, filename))
    with pytest.raises(HTTPException):
        asyncio.run(photos.get(7, filename))


def test_cloud_photos_use_private_owner_keys_and_no_local_files(monkeypatch, tmp_path):
    from vercel import blob
    put = AsyncMock()
    get = AsyncMock(return_value=SimpleNamespace(body=b'image', metadata=SimpleNamespace(content_type='image/png')))
    delete = AsyncMock()
    monkeypatch.setattr(blob, 'put_blob', put)
    monkeypatch.setattr(blob, 'get_blob', get)
    monkeypatch.setattr(blob, 'delete_blob', delete)
    missing = tmp_path / 'not-created'
    photos = Photos(SimpleNamespace(photo_storage='vercel-blob', upload_dir=missing))
    filename = 'b' * 48 + '.png'
    asyncio.run(photos.put(9, filename, b'image', 'image/png'))
    put.assert_awaited_once_with(f'farm-photos/9/{filename}', b'image', access='private', content_type='image/png')
    assert asyncio.run(photos.get(9, filename)) == (b'image', 'image/png')
    get.assert_awaited_once_with(f'farm-photos/9/{filename}', access='private')
    asyncio.run(photos.delete(9, filename))
    delete.assert_awaited_once_with(f'farm-photos/9/{filename}')
    assert not missing.exists()


def test_remote_database_keeps_sql_contract_without_creating_local_file(monkeypatch, tmp_path):
    import sqlite3
    import turso_serverless
    raw = sqlite3.connect(':memory:')
    calls = []
    def connect(url, **kwargs):
        calls.append((url, kwargs))
        return raw
    monkeypatch.setattr(turso_serverless, 'connect', connect)
    path = tmp_path / 'must-not-exist' / 'db.sqlite'
    db = Database(str(path), remote_url='turso://database.turso.io', auth_token='test-only')
    with db.connection:
        db.connection.execute('INSERT INTO users(phone) VALUES(?)', ('+919876543210',))
    user = db.connection.execute('SELECT * FROM users').fetchone()
    assert dict(user)['phone'] == '+919876543210'
    assert user[0] == user['id']
    assert calls == [('turso://database.turso.io', {'auth_token': 'test-only'})]
    assert not path.exists()
    db.close()
