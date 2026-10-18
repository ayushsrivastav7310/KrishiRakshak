"""Record the publisher's file-picker inference contract, preserving its known ambiguity."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    source = json.loads((ROOT / 'data/ml/soil-source.json').read_text())
    model = ROOT / 'artifacts/soil_model.h5'
    if hashlib.sha256(model.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Model checksum mismatch')
    labels = ['Medium Black Soil', 'Reddish Brown Soil', 'Saline Soil']
    encoder = (ROOT / 'data/ml/soil_encoder.pkl').read_bytes()
    offset = encoder.find(labels[0].encode('utf-32-le'))
    if offset < 0 or [encoder[offset+i*72:offset+(i+1)*72].decode('utf-32-le').rstrip('\x00') for i in range(3)] != labels:
        raise ValueError('Publisher encoder layout changed; review class order without unpickling')
    metadata = {'version': 'hf-' + source['revision'], 'file': model.name,
                'labels': labels, 'encoderSha256': hashlib.sha256(encoder).hexdigest(),
                'preprocessing': 'bgr_div255', 'license': 'MIT', 'sha256': source['sha256'],
                'architecture': 'VGG16-style (inspected downloaded HDF5); differs from MobileNetV2 model-card description',
                'source': 'https://huggingface.co/shrutmpatil/soil-classification-model',
                'classOrderEvidence': 'Publisher soil_encoder.pkl raw UTF-32 array inspected without unpickling; alphabetical three-class order.',
                'preprocessingEvidence': 'Publisher predict2.py: OpenCV BGR, resize 224x224 bilinear, float32 /255. Other publisher paths conflict (VGG preprocessing / double normalization).',
                'limitations': 'Uses publisher file-picker inference path. Preprocessing linkage to these exact weights not independently verified. No local accuracy or calibration evaluation; closed-set scores cannot detect unsupported soil.'}
    (ROOT / 'artifacts/soil.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (ROOT.parent / 'docs/soil-model.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('Soil metadata prepared; preprocessing uncertainty explicitly recorded.')

if __name__ == '__main__':
    main()
