"""Download public artifacts and retain source/license evidence. No dataset extraction paths trusted."""
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fetch(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read()

def main():
    data = ROOT / 'data' / 'ml'
    artifacts = ROOT / 'artifacts'
    data.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(exist_ok=True)
    listing = json.loads(fetch('https://www.kaggle.com/api/v1/datasets/list?search=atharvaingle'))
    crop = next(row for row in listing if row['ref'] == 'atharvaingle/crop-recommendation-dataset')
    if crop['licenseName'] != 'Apache 2.0':
        raise RuntimeError('Dataset license changed; review before downloading.')
    (data / 'crop-source.json').write_text(json.dumps(crop, indent=2), encoding='utf-8')
    (data / 'crop-description.json').write_bytes(fetch('https://www.kaggle.com/api/v1/datasets/view/atharvaingle/crop-recommendation-dataset'))
    archive = zipfile.ZipFile(io.BytesIO(fetch('https://www.kaggle.com/api/v1/datasets/download/atharvaingle/crop-recommendation-dataset?datasetVersionNumber=1')))
    name = next(name for name in archive.namelist() if name.endswith('Crop_recommendation.csv'))
    (data / 'Crop_recommendation.csv').write_bytes(archive.read(name))
    model_info = json.loads(fetch('https://huggingface.co/api/models/shrutmpatil/soil-classification-model'))
    revision = model_info['sha']
    model = fetch(f'https://huggingface.co/shrutmpatil/soil-classification-model/resolve/{revision}/soil_model.h5')
    (artifacts / 'soil_model.h5').write_bytes(model)
    (data / 'soil-source.json').write_text(json.dumps({'revision': revision, 'sha256': hashlib.sha256(model).hexdigest(), 'info': model_info}, indent=2), encoding='utf-8')
    upstream = 'https://raw.githubusercontent.com/shrutmpatil/Machine-Learning-Framework-for-Soil-Classification-and-Nutrient-Aware-Crop-Recommendation/main/'
    for name in ['soil_encoder.pkl', 'predict.py', 'predict2.py', 'data_collection.py', 'data_preprocessing.py', 'train_model.py', 'train2_model.py', 'LICENSE']:
        (data / name).write_bytes(fetch(upstream + name))
    print('Downloaded crop dataset, soil weights and upstream evidence to ignored local storage.')

if __name__ == '__main__':
    main()
