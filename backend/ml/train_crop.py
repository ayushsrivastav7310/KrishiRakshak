"""Reproducible fixed holdout evaluation; no hyperparameter search on test data."""
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from app.intelligence import FEATURES, UNITS, CropInput

ROOT = Path(__file__).resolve().parents[1]

def main():
    started = time.time()
    source = ROOT / 'data/ml/Crop_recommendation.csv'
    license_info = json.loads((source.parent / 'crop-source.json').read_text())
    if license_info['licenseName'] != 'Apache 2.0':
        raise ValueError('License review required')
    frame = pd.read_csv(source)
    if set(frame.columns) != set(FEATURES + ['label']):
        raise ValueError('Unexpected dataset schema')
    original = len(frame)
    if frame.isna().any().any():
        raise ValueError('Missing values: repair and document the source first')
    for row in frame.to_dict('records'):
        CropInput(**{key: row[key] for key in FEATURES})
    if frame.groupby(FEATURES)['label'].nunique().max() > 1:
        raise ValueError('Conflicting labels for identical features')
    frame = frame.drop_duplicates(subset=FEATURES).reset_index(drop=True)
    if frame.label.str.strip().ne(frame.label).any() or frame.label.str.len().eq(0).any():
        raise ValueError('Inconsistent labels')
    train, test = train_test_split(np.arange(len(frame)), test_size=.2, random_state=42, stratify=frame.label)
    X = frame[FEATURES].to_numpy(dtype=float)
    y = frame.label.to_numpy()
    model = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    model.fit(X[train], y[train])
    dummy = DummyClassifier(strategy='most_frequent').fit(X[train], y[train])
    labels = list(model.classes_)
    def evaluate(estimator):
        pred = estimator.predict(X[test])
        return {'accuracy': accuracy_score(y[test], pred), 'macroF1': f1_score(y[test], pred, average='macro'),
                'perClass': classification_report(y[test], pred, labels=labels, output_dict=True, zero_division=0),
                'confusionMatrix': confusion_matrix(y[test], pred, labels=labels).tolist()}
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {'source': license_info['url'], 'license': 'Apache-2.0', 'datasetSha256': sha,
              'originalRows': original, 'rows': len(frame), 'duplicatesRemoved': original-len(frame),
              'missingValues': 0, 'classCounts': frame.label.value_counts().to_dict(),
              'split': {'train': len(train), 'test': len(test), 'seed': 42, 'stratified': True},
              'randomForest': evaluate(model), 'majorityBaseline': evaluate(dummy), 'labels': labels,
              'hardware': platform.platform() + ' / ' + platform.processor(), 'epochs': 'not applicable to Random Forest',
              'sklearn': sklearn.__version__, 'seconds': time.time()-started,
              'limitations': 'Observational/synthetic provenance not independently verified. Rainfall accumulation period unspecified. NPK described as soil content ratios by publisher, no laboratory protocol; NPK measurement units are unspecified; values must match the dataset scale. Direct conversion from soil tests is unvalidated. Holdout classification is not yield improvement.'}
    artifact = ROOT / 'artifacts'
    artifact.mkdir(exist_ok=True)
    joblib.dump(model, artifact / 'crop.joblib', compress=3)
    metadata = {'version': 'rf-v1-' + sha[:12], 'features': FEATURES, 'units': UNITS, 'labels': labels,
                'sha256': hashlib.sha256((artifact / 'crop.joblib').read_bytes()).hexdigest(),
                'ranges': {key: [float(frame[key].min()), float(frame[key].max())] for key in FEATURES},
                'preprocessing': 'float64; no scaling; reject missing/nonfinite/out-of-range inputs',
                'soilTypeUsed': False, 'rainfallPeriod': 'unspecified by dataset publisher',
                'unitCaveat': report['limitations'], 'source': report['source'], 'license': report['license']}
    (artifact / 'crop.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    out = ROOT.parent / 'docs'
    (out / 'crop-evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out / 'crop-split.json').write_text(json.dumps({'datasetSha256': sha, 'train': train.tolist(), 'test': test.tolist()}), encoding='utf-8')
    pd.DataFrame(report['randomForest']['confusionMatrix'], index=labels, columns=labels).to_csv(out / 'crop-confusion-matrix.csv')
    print(json.dumps({key: report[key] for key in ['rows', 'split', 'seconds']}))
    print('Random Forest:', report['randomForest']['accuracy'], report['randomForest']['macroF1'])
    print('Majority baseline:', report['majorityBaseline']['accuracy'], report['majorityBaseline']['macroF1'])

if __name__ == '__main__':
    main()

