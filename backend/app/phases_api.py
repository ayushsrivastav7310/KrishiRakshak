from typing import Annotated, Literal
from fastapi import APIRouter, Depends, File, Form, UploadFile, Query
from starlette.concurrency import run_in_threadpool
from app.diseases import DiseaseModel
from app.intelligence import validated_image
from app.phase_store import migrate, record, history
from app.irrigation import IrrigationInput, IrrigationLog, irrigation_weather, calculate
from app.mandi import MandiService, Comparison, compare, prices

def phases_router(db, current_user, directory, api_key=''):
    migrate(db)
    router = APIRouter(prefix='/api', tags=['Farm support'])
    User = Annotated[dict, Depends(current_user)]
    disease = DiseaseModel(directory)
    mandi = MandiService(db,api_key)

    @router.get('/diseases/model-info')
    def model_info(user: User): return disease.info()

    @router.get('/diseases/supported')
    def supported(user: User):
        info = disease.info()
        return {'available': info['available'], 'crops': sorted({x.split('___')[0] for x in info.get('labels',[])})}

    @router.post('/diseases/predict')
    async def predict(user: User, crop: str = Form(min_length=1,max_length=80), photo: UploadFile = File(...)):
        try: data = await photo.read(5*1024*1024+1)
        finally: await photo.close()
        def infer():
            image = validated_image(data,photo.content_type)
            result = disease.predict(image,crop)
            result['id'] = record(db,user['id'],'disease',result)
            return result
        return await run_in_threadpool(infer)

    @router.get('/diseases/history')
    def disease_history(user: User): return {'history':history(db,user['id'],'disease')}

    @router.get('/irrigation/weather')
    async def get_weather(user: User, latitude: float = Query(ge=-90,le=90,allow_inf_nan=False), longitude: float = Query(ge=-180,le=180,allow_inf_nan=False)):
        return await irrigation_weather(latitude,longitude)

    @router.post('/irrigation/calculate')
    async def irrigation_calculate(body: IrrigationInput, user: User):
        result = calculate(body,await irrigation_weather(body.latitude,body.longitude))
        result['id'] = record(db,user['id'],'recommendation',result)
        return result

    @router.get('/irrigation/recommendations')
    def recommendations(user: User): return {'history':history(db,user['id'],'recommendation')}

    @router.post('/irrigation/log')
    def log(body: IrrigationLog, user: User):
        result = body.model_dump(mode='json')
        result['volumeLiters'] = body.depthMm*body.areaM2
        result['source'] = 'farmer-recorded'
        return {'id':record(db,user['id'],'irrigation',result),**result}

    @router.get('/irrigation/history')
    def irrigation_history(user: User): return {'history':history(db,user['id'],'irrigation')}

    @router.get('/mandi/prices')
    def mandi_prices(user: User, state: str = Query(default='',max_length=150), district: str = Query(default='',max_length=150), commodity: str = Query(default='',max_length=150), market: str = Query(default='',max_length=150), limit: int = Query(default=50,ge=1,le=200), offset: int = Query(default=0,ge=0), sort: Literal['latest','modal'] = 'latest'):
        return prices(db,state,district,commodity,market,limit,offset,sort)

    @router.post('/mandi/sync')
    async def sync(user: User, state: str = Query(default='',max_length=150), commodity: str = Query(default='',max_length=150)):
        await mandi.sync(state,commodity)
        return {'status':mandi.status}

    @router.get('/mandi/sync-status')
    def sync_status(user: User):
        with db.lock:
            row=db.connection.execute('SELECT count(*),max(synced_at),max(date) FROM mandi_prices').fetchone()
        return {'status':mandi.status,'count':row[0],'lastSync':row[1],'latestReportingDate':row[2],
                'coverage':'Synchronization retrieves at most 1,000 source records. This is partial coverage; use CSV imports for complete archives.'}

    @router.get('/mandi/markets')
    def markets(user: User):
        with db.lock:
            return {'markets':[dict(r) for r in db.connection.execute('SELECT DISTINCT state,district,market FROM mandi_prices ORDER BY state,district,market LIMIT 2000')]}

    @router.get('/mandi/commodities')
    def commodities(user: User):
        with db.lock: return {'commodities':[r[0] for r in db.connection.execute('SELECT DISTINCT commodity FROM mandi_prices ORDER BY commodity')]}

    @router.get('/mandi/history')
    def market_history(user: User, commodity: str = Query(min_length=1,max_length=150), market: str = Query(min_length=1,max_length=150), state: str = Query(min_length=1,max_length=150), district: str = Query(min_length=1,max_length=150), variety: str = Query(min_length=1,max_length=150)):
        with db.lock:
            rows=[dict(r) for r in db.connection.execute('SELECT date,modal,unit,source FROM mandi_prices WHERE commodity=? AND market=? AND state=? AND district=? AND variety=? ORDER BY date LIMIT 366',(commodity,market,state,district,variety))]
        return {'observations':rows,'sufficientForTrend':len({r['date'] for r in rows})>=2}

    @router.get('/mandi/msp')
    def msp(user: User, crop: str = Query(min_length=1,max_length=150), variety: str = Query(min_length=1,max_length=150), season: str = Query(min_length=1,max_length=100), priceId: int | None = Query(default=None,gt=0)):
        with db.lock:
            rows=[dict(r) for r in db.connection.execute('SELECT * FROM msp_records WHERE crop=? COLLATE NOCASE AND variety=? COLLATE NOCASE AND season=?',(crop,variety,season))]
            if priceId:
                observation=db.connection.execute('SELECT * FROM mandi_prices WHERE id=?',(priceId,)).fetchone()
                for row in rows:
                    compatible=observation and observation['commodity'].casefold()==crop.casefold() and observation['variety'].casefold()==variety.casefold() and row['period_start'] and row['period_end'] and row['period_start']<=observation['date']<=row['period_end']
                    row['difference']=round(observation['modal']-row['price'],2) if compatible else None
                    row['comparable']=bool(compatible)
        return {'records':rows,'notice':'MSP is season- and variety-specific. It is not a guaranteed transaction price or a universal private-sale minimum.'}

    @router.post('/mandi/compare')
    def comparison(body: Comparison, user: User): return compare(db,body)

    return router
