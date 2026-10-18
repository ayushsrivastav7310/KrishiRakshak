"""Actual local upload/inference smoke; one image is not an accuracy benchmark."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from fastapi.testclient import TestClient
from app.api import create_app
from test_api import CONFIG,ORIGIN,login

app=create_app({**CONFIG,'UPLOAD_DIR':str(ROOT/'backend/data/disease-smoke/uploads')})
with TestClient(app,headers={'Origin':ORIGIN}) as client:
    login(client)
    with (ROOT/'backend/data/disease-smoke/leaf.jpg').open('rb') as photo:
        response=client.post('/api/diseases/predict',data={'crop':'Tomato'},files={'photo':('leaf.jpg',photo,'image/jpeg')})
    assert response.status_code==200,response.text
    result=response.json()
    result['testNote']='Single public PlantVillage image smoke test, potentially seen by the pretrained model; not held-out evaluation or accuracy.'
    result['imageSource']=json.loads((ROOT/'backend/data/disease-smoke/source.json').read_text())
    (ROOT/'docs/disease-smoke.json').write_text(json.dumps(result,indent=2))
    assert len(client.get('/api/diseases/history').json()['history'])==1
    print(json.dumps({k:result[k] for k in ['label','confidence','uncertain','modelVersion','testNote']},indent=2))
