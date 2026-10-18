"""Local model registry. Missing or incompatible artifacts fail closed."""
import io
import hashlib
import json
import warnings
from functools import lru_cache
from pathlib import Path
from threading import RLock

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.models import Number

FEATURES = ['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']
UNITS = dict(zip(FEATURES, ['dataset ratio (unit unspecified)', 'dataset ratio (unit unspecified)', 'dataset ratio (unit unspecified)', '°C', '%', 'pH', 'mm']))
ARTIFACTS = Path(__file__).resolve().parents[1] / 'artifacts'

@lru_cache(maxsize=4)
def get_registry(directory):
    return ModelRegistry(directory)

class CropInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    N: Number = Field(ge=0, le=1000)
    P: Number = Field(ge=0, le=1000)
    K: Number = Field(ge=0, le=1000)
    temperature: Number = Field(ge=-50, le=65)
    humidity: Number = Field(ge=0, le=100)
    ph: Number = Field(ge=0, le=14)
    rainfall: Number = Field(ge=0, le=10000)
    soilType: str = Field(default='', max_length=80)
    soilSource: Literal['farmer-provided', 'image-estimate'] = 'farmer-provided'
    nutrientSource: Literal['farmer-provided', 'soil-test'] = 'farmer-provided'
    temperatureSource: Literal['farmer-provided', 'weather-estimate'] = 'farmer-provided'
    humiditySource: Literal['farmer-provided', 'weather-estimate'] = 'farmer-provided'
    rainfallSource: Literal['farmer-provided', 'historical-record'] = 'farmer-provided'

def validated_image(data, content_type):
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, 'Choose an image up to 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}.get(image.format) != content_type:
                    raise ValueError()
                if image.width * image.height > 20_000_000:
                    raise ValueError()
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                return image.convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, 'Choose a valid JPEG, PNG or WebP image (maximum 20 megapixels).') from None

class ModelRegistry:
    def __init__(self, directory=ARTIFACTS):
        self.directory = Path(directory)
        self.lock = RLock()
        self.models = {}
        self.details = {}
        self.errors = {}
        for name in ['soil', 'crop']:
            try:
                metadata = json.loads((self.directory / f'{name}.json').read_text(encoding='utf-8'))
                artifact = self.directory / ('crop.joblib' if name == 'crop' else metadata['file'])
                if metadata.get('sha256') and hashlib.sha256(artifact.read_bytes()).hexdigest() != metadata['sha256']:
                    raise ValueError('Artifact checksum mismatch')
                if name == 'crop':
                    import joblib
                    if metadata['features'] != FEATURES or metadata['units'] != UNITS:
                        raise ValueError('Feature contract mismatch')
                    model = joblib.load(self.directory / 'crop.joblib')
                    if list(model.classes_) != metadata['labels']:
                        raise ValueError('Crop labels mismatch')
                else:
                    import tensorflow as tf
                    model = tf.keras.models.load_model(self.directory / metadata['file'], compile=False)
                    if tuple(model.input_shape[1:]) != (224, 224, 3) or model.output_shape[-1] != len(metadata['labels']):
                        raise ValueError('Soil shape mismatch')
                    if metadata['preprocessing'] not in ['rgb_mobilenet_v2', 'bgr_div255', 'bgr_div65025']:
                        raise ValueError('Unknown preprocessing')
                self.models[name], self.details[name] = model, metadata
            except Exception as exc:
                self.errors[name] = type(exc).__name__

    def require(self, name):
        if name not in self.models:
            raise HTTPException(503, f'{name.title()} model unavailable. Install ML dependencies and prepare verified artifacts; see docs/PHASE_2_SETUP.md.')
        return self.models[name], self.details[name]

    def metadata(self):
        return {name: {'available': name in self.models, **self.details.get(name, {}),
                       'loadError': self.errors.get(name)} for name in ['soil', 'crop']}

    def soil(self, image):
        model, meta = self.require('soil')
        import numpy as np
        if meta['preprocessing'].startswith('bgr_'):
            import cv2
            array = cv2.resize(np.asarray(image)[:, :, ::-1], (224, 224)).astype('float32')
            array /= 65025.0 if meta['preprocessing'] == 'bgr_div65025' else 255.0
        else:
            import tensorflow as tf
            array = tf.image.resize(np.asarray(image), (224, 224)).numpy().astype('float32') / 127.5 - 1
        with self.lock:
            inputs = [array[None]] if isinstance(model.input, list) else array[None]
            scores = np.asarray(model(inputs, training=False))[0]
        if not np.isfinite(scores).all() or (scores < 0).any() or not np.isclose(scores.sum(), 1, atol=.01):
            raise HTTPException(503, 'Soil model returned invalid probabilities.')
        index = int(scores.argmax())
        return {'soilType': meta['labels'][index], 'confidence': float(scores[index]),
                'uncertain': bool(scores[index] < .7), 'modelVersion': meta['version'],
                'supportedClasses': meta['labels'],
                'limitations': 'Closed-set visual estimate: unsupported soils and non-soil photos may receive high scores. Cannot measure NPK, pH or moisture. Confirm manually. ' + meta.get('limitations', '')}

    def crop(self, body):
        model, meta = self.require('crop')
        values = body.model_dump()
        outside = [key for key in FEATURES if not meta['ranges'][key][0] <= values[key] <= meta['ranges'][key][1]]
        if outside:
            raise HTTPException(400, 'Outside training range: ' + ', '.join(outside) + '. See model metadata for supported ranges.')
        with self.lock:
            scores = model.predict_proba([[values[key] for key in FEATURES]])[0]
        ranked = sorted(zip(model.classes_, scores), key=lambda pair: pair[1], reverse=True)[:3]
        return {'recommendedCrop': str(ranked[0][0]), 'suggestions': [{'crop': str(crop), 'score': float(score)} for crop, score in ranked],
                'scoreLabel': 'Random Forest vote share; not calibrated suitability or yield probability',
                'inputs': values, 'modelVersion': meta['version'], 'soilTypeUsed': False,
                'considerations': 'Check local season, water availability, drainage, seed availability and soil-test results with a local agronomist. Dataset rainfall period is unspecified; current weather is only an estimate and does not match seasonal growing conditions.'}

