from typing import Annotated
from fastapi import APIRouter, Depends, File, Query, UploadFile, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.intelligence import CropInput, ModelRegistry, validated_image
from app.weather import weather

class Correction(BaseModel):
    analysisId: int = Field(gt=0)
    soilType: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')

def intelligence_router(database, current_user, registry):
    router = APIRouter(prefix='/api', tags=['Crop Intelligence'])
    User = Annotated[dict, Depends(current_user)]

    @router.get('/models/metadata')
    def metadata(user: User):
        return registry.metadata()

    @router.get('/crops/supported')
    def supported(user: User):
        _, meta = registry.require('crop')
        return {'crops': meta['labels'], 'features': meta['features'], 'units': meta['units'], 'ranges': meta['ranges'], 'soilTypeUsed': False}

    @router.post('/soil/predict')
    async def predict(user: User, photo: UploadFile = File(...)):
        try:
            data = await photo.read(5 * 1024 * 1024 + 1)
        finally:
            await photo.close()
        def inference():
            image = validated_image(data, photo.content_type)
            result = registry.soil(image)
            result['id'] = database.record(user['id'], 'soil', result)
            return result
        return await run_in_threadpool(inference)

    @router.post('/soil/correction')
    def correction(body: Correction, user: User):
        with database.lock:
            row = database.connection.execute("SELECT id FROM intelligence_history WHERE id=? AND user_id=? AND kind='soil'", (body.analysisId, user['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Soil analysis not found.')
        result = {**body.model_dump(), 'source': 'farmer-provided'}
        return {'id': database.record(user['id'], 'correction', result), **result}

    @router.post('/crops/recommend')
    def recommend(body: CropInput, user: User):
        result = registry.crop(body)
        result['id'] = database.record(user['id'], 'crop', result)
        return result

    @router.get('/weather')
    async def get_weather(user: User, latitude: float = Query(ge=-90, le=90, allow_inf_nan=False), longitude: float = Query(ge=-180, le=180, allow_inf_nan=False)):
        return await weather(latitude, longitude)

    @router.get('/intelligence/history')
    def history(user: User):
        return {'history': database.history(user['id'])}

    return router
