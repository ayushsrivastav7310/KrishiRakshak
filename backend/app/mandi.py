"""Government observations only. CSV ingestion is an explicit operator action."""
import csv
import json
import math
import os
import asyncio
import time
from datetime import date, datetime, timezone
from urllib.parse import urlparse
import httpx2 as httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

RESOURCE='9ef84268-d588-465a-a308-a864a43d0070'
SOURCE='https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi'

def parse_price(row, source=SOURCE, unit='INR/quintal'):
    if unit not in ['INR/quintal','INR/kg']: raise ValueError('Unsupported price unit')
    prices=[float(row[k]) for k in ['min_price','max_price','modal_price']]
    if not all(math.isfinite(x) and x>=0 for x in prices) or not prices[0]<=prices[2]<=prices[1]: raise ValueError('Invalid price range')
    raw_date=row['arrival_date']
    try: day=datetime.strptime(raw_date,'%d/%m/%Y').date()
    except ValueError: day=date.fromisoformat(raw_date)
    if day>date.today(): raise ValueError('Future reporting date')
    fields=[str(row[k]).strip() for k in ['state','district','market','commodity','variety']]
    if any(not x or len(x)>150 for x in fields): raise ValueError('Missing market identifiers')
    factor=100 if unit=='INR/kg' else 1
    return (*fields,day.isoformat(),*(x*factor for x in prices),'INR/quintal',source,
            json.dumps({'values':row,'unit':unit}),datetime.now(timezone.utc).isoformat())

def ingest(db, rows, source=SOURCE, unit='INR/quintal'):
    parsed=[parse_price(row,source,unit) for row in rows]
    with db.lock,db.connection:
        db.connection.executemany('''INSERT INTO mandi_prices(state,district,market,commodity,variety,date,minimum,maximum,modal,unit,source,original,synced_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(state,district,market,commodity,variety,date,source)
        DO UPDATE SET minimum=excluded.minimum,maximum=excluded.maximum,modal=excluded.modal,original=excluded.original,synced_at=excluded.synced_at''',parsed)
    return len(parsed)

def prices(db,state='',district='',commodity='',market='',limit=50,offset=0,sort='latest'):
    clauses,params=[],[]
    for key,value in [('state',state),('district',district),('commodity',commodity)]:
        if value: clauses.append(f'{key}=? COLLATE NOCASE'); params.append(value)
    if market: clauses.append('instr(lower(market),lower(?))>0'); params.append(market)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    with db.lock:
        total=db.connection.execute('SELECT count(*) FROM mandi_prices'+where,params).fetchone()[0]
        order='modal DESC,date DESC,id' if sort=='modal' else 'date DESC,modal DESC,id'
        rows=db.connection.execute('SELECT * FROM mandi_prices'+where+' ORDER BY '+order+' LIMIT ? OFFSET ?',(*params,limit,offset)).fetchall()
    return {'records':[{**dict(r),'stale':(date.today()-date.fromisoformat(r['date'])).days>2} for r in rows], 'total':total,'limit':limit,'offset':offset,
            'notice':'Government-reported observations, not guaranteed purchase offers. Prices may be historical.'}

class MandiService:
    def __init__(self,db,api_key=None):
        self.db=db; self.api_key=api_key; self.synced={}; self.status='not-synchronized'
    async def sync(self,state='',commodity=''):
        key=self.api_key if self.api_key is not None else os.getenv('DATA_GOV_API_KEY','')
        if not key: raise HTTPException(503,'Government API key is not configured. Import an official CSV using backend/ml/import_markets.py.')
        scope=(state,commodity)
        if time.monotonic()-self.synced.get(scope,0)<900: return
        params={'api-key':key,'format':'json','limit':1000,'offset':0}
        if state: params['filters[state]']=state
        if commodity: params['filters[commodity]']=commodity
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for attempt in range(2):
                    response=await client.get(f'https://api.data.gov.in/resource/{RESOURCE}',params=params)
                    if response.status_code not in [429,502,503,504]: break
                    if attempt==0: await asyncio.sleep(.5)
                if response.status_code in [401,403]:
                    self.status='credentials-rejected'; raise HTTPException(502,'Government API rejected credentials.')
                response.raise_for_status(); payload=response.json()
            if 'records' not in payload or not isinstance(payload['records'],list): raise ValueError()
            ingest(self.db,payload['records'])
            self.synced[scope]=time.monotonic(); self.status='partial-page-synchronized'
        except (httpx.HTTPError,ValueError,KeyError,TypeError):
            self.status='source-unavailable'
            raise HTTPException(502,'Government data unavailable or incompatible. Stored observations remain available.') from None

class MarketOption(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    priceId: int=Field(gt=0)
    distanceKm: float=Field(ge=0,le=10000)
    transportPerKm: float=Field(ge=0,le=100000)
    handlingCost: float=Field(default=0,ge=0,le=10000000)

class Comparison(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    commodity: str=Field(min_length=1,max_length=150)
    variety: str=Field(min_length=1,max_length=150)
    quantityQuintals: float=Field(gt=0,le=1000000)
    options: list[MarketOption]=Field(min_length=1,max_length=30)

def compare(db,body):
    results=[]
    with db.lock:
        for option in body.options:
            row=db.connection.execute('SELECT * FROM mandi_prices WHERE id=?',(option.priceId,)).fetchone()
            if not row: raise HTTPException(404,'Price observation not found')
            if row['commodity'].casefold()!=body.commodity.casefold() or row['variety'].casefold()!=body.variety.casefold():
                raise HTTPException(400,'Compare only matching commodities and varieties.')
            gross=row['modal']*body.quantityQuintals
            transport=option.distanceKm*option.transportPerKm
            results.append({'priceId':row['id'],'market':row['market'],'reportingDate':row['date'],
                'stale':(date.today()-date.fromisoformat(row['date'])).days>2,
                'gross':round(gross,2),'transportCost':round(transport,2),'handlingCost':option.handlingCost,
                'net':round(gross-transport-option.handlingCost,2)})
    return {'options':sorted(results,key=lambda r:r['net'],reverse=True),
            'notice':'Estimated proceeds from reported prices; confirm grade, date, buyer terms and all costs. Distance and trip cost are farmer estimates.'}

def import_msp(db,rows):
    parsed=[]
    for row in rows:
        host=(urlparse(row['source']).hostname or '').lower()
        if not host.endswith(('.gov.in','.nic.in')) or not row['source'].startswith('https://'): raise ValueError('Official notification URL required')
        price=float(row['price'])
        if not math.isfinite(price) or price<=0 or row['unit']!='INR/quintal': raise ValueError('Invalid MSP')
        if any(not row[k].strip() for k in ['crop','variety','season']): raise ValueError('Crop, variety and season required')
        start,end=date.fromisoformat(row['period_start']),date.fromisoformat(row['period_end'])
        if end<start:raise ValueError('Invalid marketing season period')
        parsed.append(tuple(row[k] for k in ['crop','variety','season'])+(price,row['unit'],row['source'],start.isoformat(),end.isoformat()))
    with db.lock,db.connection:
        db.connection.executemany('INSERT OR REPLACE INTO msp_records(crop,variety,season,price,unit,source,period_start,period_end) VALUES(?,?,?,?,?,?,?,?)',parsed)
    return len(parsed)
