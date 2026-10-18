"""Owner-scoped photo keys; cloud objects stay private behind the existing API."""
import re
from fastapi import HTTPException


class Photos:
    def __init__(self, settings):
        self.cloud = settings.photo_storage == 'vercel-blob'
        self.directory = settings.upload_dir
        if not self.cloud:
            self.directory.mkdir(parents=True, exist_ok=True)

    def key(self, user_id, filename):
        if not re.fullmatch(r'[0-9a-f]{48}\.(jpg|png|webp)', filename):
            raise HTTPException(404, 'Photo not found.')
        return f'farm-photos/{user_id}/{filename}'

    async def put(self, user_id, filename, data, mime):
        key = self.key(user_id, filename)
        if self.cloud:
            from vercel import blob
            await blob.put_blob(key, data, access='private', content_type=mime)
        else:
            (self.directory / filename).write_bytes(data)

    async def get(self, user_id, filename):
        key = self.key(user_id, filename)
        if self.cloud:
            from vercel import blob
            try:
                result = await blob.get_blob(key, access='private')
            except blob.BlobNotFoundError:
                raise HTTPException(404, 'No soil photo saved.') from None
            return result.body, result.metadata.content_type or 'application/octet-stream'
        path = self.directory / filename
        if not path.is_file():
            raise HTTPException(404, 'No soil photo saved.')
        mime = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}[filename.rsplit('.', 1)[1]]
        return path.read_bytes(), mime

    async def delete(self, user_id, filename):
        key = self.key(user_id, filename)
        if self.cloud:
            from vercel import blob
            await blob.delete_blob(key)
        else:
            (self.directory / filename).unlink(missing_ok=True)
