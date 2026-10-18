"""Local, checksum-verified Keras inference. Never substitutes predictions."""
import hashlib
import json
from pathlib import Path
from threading import RLock
from fastapi import HTTPException

GENERAL = {
    'description': 'Preliminary visual classification; field confirmation is required.',
    'symptoms': 'Inspect both leaf surfaces and the whole plant; record spots, yellowing, wilting and spread.',
    'prevention': 'Use clean tools and healthy planting material. Monitor nearby plants and avoid moving affected material between fields.',
    'consult': 'Consult your local agricultural extension service when symptoms spread, plants wilt, or the result is uncertain.',
    'source': 'https://ipm.ucanr.edu/PMG/crops-agriculture.html',
}
CURATED = {
    'Tomato___Early_blight': {'description':'Early blight is a fungal disease that can affect tomato leaves, stems and fruit.',
        'symptoms':'Older leaves may develop brown lesions with concentric rings and surrounding yellowing.',
        'prevention':'Use healthy transplants, rotate away from susceptible crops, and reduce prolonged leaf wetness.',
        'source':'https://ipm.ucanr.edu/agriculture/tomato/early-blight/'},
    'Tomato___Late_blight': {'description':'Late blight is a potentially fast-spreading disease caused by Phytophthora infestans.',
        'symptoms':'Look for water-soaked lesions that enlarge and darken; whitish growth may occur in humid conditions.',
        'prevention':'Monitor crops closely in cool, wet weather and obtain local extension advice promptly when spread is suspected.',
        'source':'https://ipm.ucanr.edu/agriculture/tomato/late-blight/'},
}

class DiseaseModel:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = RLock()
        self.model = None
        self.meta = {}

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            try:
                meta = json.loads((self.directory / 'disease.json').read_text())
                if meta.get('framework') == 'transformers':
                    folder = self.directory / 'disease-hf'
                    for filename, digest in meta['checksums'].items():
                        if Path(filename).name != filename or hashlib.sha256((folder/filename).read_bytes()).hexdigest() != digest:
                            raise ValueError('Checksum mismatch')
                    from transformers import AutoModelForImageClassification, MobileNetV2ImageProcessorPil
                    self.processor = MobileNetV2ImageProcessorPil.from_pretrained(folder, local_files_only=True)
                    model = AutoModelForImageClassification.from_pretrained(folder, local_files_only=True, trust_remote_code=False, use_safetensors=True)
                    model.eval()
                    if [model.config.id2label[i] for i in range(model.config.num_labels)] != meta['labels']:
                        raise ValueError('Label mismatch')
                    self.model,self.meta = model,meta
                    return
                path = (self.directory / meta['file']).resolve()
                if path.parent != self.directory.resolve() or path.suffix != '.keras':
                    raise ValueError('Unsafe artifact path')
                if not meta.get('license') or not meta.get('version') or meta['preprocessing'] != 'rgb_mobilenet_v2':
                    raise ValueError('Unverified model contract')
                if hashlib.sha256(path.read_bytes()).hexdigest() != meta['sha256']:
                    raise ValueError('Checksum mismatch')
                labels = meta['labels']
                if not labels or len(set(labels)) != len(labels) or not all('___' in x for x in labels):
                    raise ValueError('Invalid labels')
                import tensorflow as tf
                model = tf.keras.models.load_model(path, compile=False, safe_mode=True)
                if tuple(model.input_shape[1:]) != (224, 224, 3) or model.output_shape[-1] != len(labels):
                    raise ValueError('Incompatible shape')
                self.model, self.meta = model, meta
            except Exception:
                raise HTTPException(503, 'Disease model unavailable. See docs/PHASE_3_DISEASE_DETECTION.md for verified artifact setup.') from None

    def info(self):
        try:
            self.load()
        except HTTPException:
            return {'available': False, 'reason': 'Verified disease artifact is not installed.', 'metrics': None}
        return {'available': True, **self.meta}

    def predict(self, image, crop):
        self.load()
        import numpy as np
        labels = self.meta['labels']
        supported = {label.split('___')[0] for label in labels}
        if crop not in supported:
            raise HTTPException(400, 'Select a supported crop.')
        with self.lock:
            if self.meta.get('framework') == 'transformers':
                import torch
                with torch.inference_mode():
                    logits = self.model(**self.processor(images=image,return_tensors='pt')).logits
                    scores = torch.softmax(logits,dim=-1)[0].cpu().numpy()
            else:
                scores = np.asarray(self.model(np.asarray(image.resize((224, 224)), dtype='float32')[None] / 127.5 - 1, training=False))[0]
        if scores.shape != (len(labels),) or not np.isfinite(scores).all() or (scores < 0).any() or not np.isclose(scores.sum(), 1, atol=.01):
            raise HTTPException(503, 'Invalid model output.')
        order = np.argsort(scores)[::-1]
        top = int(order[0])
        mismatch = labels[top].split('___')[0] != crop
        gray = np.asarray(image.resize((128,128)).convert('L'),dtype=float)
        unclear = min(image.size)<128 or gray.std()<8
        uncertain = float(scores[top]) < .85 or float(scores[top] - scores[order[1]]) < .15 or mismatch or unclear
        return {'label': labels[top], 'crop': crop, 'confidence': float(scores[top]),
                'uncertain': bool(uncertain), 'cropMismatch': mismatch, 'imageUnclear':bool(unclear),
                'warning': 'Confidence is a model score, not diagnostic accuracy. Controlled leaf datasets may not generalize to field images.',
                'alternatives': [{'label': labels[int(i)], 'confidence': float(scores[i])} for i in order[1:4]],
                'guidance': {**GENERAL,**CURATED.get(labels[top],{})}, 'modelVersion': self.meta['version']}
