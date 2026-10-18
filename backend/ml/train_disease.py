"""Reproducible MobileNetV2 training from a licensed, leaf-grouped manifest.

CSV columns: path,label,leaf_group,split (train/validation/test).
Use the official grouped test set; split training groups for validation.
Paths resolve relative to the manifest. No datasets are bundled.
"""
import argparse
import hashlib
import json
from pathlib import Path

def prepare(manifest):
    import pandas as pd
    import imagehash
    from PIL import Image
    frame = pd.read_csv(manifest)
    required = {'path', 'label', 'leaf_group', 'split'}
    if not required.issubset(frame.columns) or frame[list(required)].isna().any().any():
        raise ValueError('Manifest requires path,label,leaf_group,split without missing values')
    if set(frame.split) != {'train', 'validation', 'test'}:
        raise ValueError('All three explicit splits required')
    if frame.groupby('leaf_group').split.nunique().max() != 1:
        raise ValueError('Leaf group leakage')
    seen, hashes, rows, rejected = {}, {}, [], []
    for row in frame.to_dict('records'):
        path = (Path(manifest).resolve().parent / row['path']).resolve()
        try:
            with Image.open(path) as im:
                im.load()
                digest = hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()
                perceptual = imagehash.phash(im)
        except (OSError, ValueError):
            rejected.append(str(path))
            continue
        if digest in seen:
            if seen[digest] != (row['split'], row['label']):
                raise ValueError('Exact duplicate leakage or conflicting label')
            continue
        # Exhaustive Hamming-distance audit, never silently overlooks cross-split neighbors.
        for previous, split in hashes.values():
            if split != row['split'] and perceptual - previous <= 4:
                raise ValueError('Near-duplicate across splits; regroup and rerun')
        seen[digest] = (row['split'], row['label'])
        hashes[digest] = (perceptual, row['split'])
        rows.append({**row, 'path': str(path), 'sha256': digest})
    clean = pd.DataFrame(rows)
    labels = sorted(clean.label.unique())
    for split in ['train', 'validation', 'test']:
        if set(clean[clean.split == split].label) != set(labels):
            raise ValueError('Every class must occur in every split')
    return clean, labels, rejected

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest')
    parser.add_argument('--license', required=True, help='Verified dataset license and attribution')
    parser.add_argument('--output', default='backend/artifacts')
    parser.add_argument('--baseline', help='Optional compatible original .keras model, same labels/preprocessing')
    args = parser.parse_args()
    import numpy as np
    import tensorflow as tf
    import matplotlib.pyplot as plt
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    tf.keras.utils.set_random_seed(42)
    tf.config.experimental.enable_op_determinism()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    frame, labels, rejected = prepare(args.manifest)
    frame.to_csv(out / 'disease-split.csv', index=False)
    (out / 'disease-data-audit.json').write_text(json.dumps({'counts':frame.groupby(['split','label']).size().reset_index(name='count').to_dict('records'), 'corrupt': rejected},indent=2))
    def dataset(split):
        part = frame[frame.split == split]
        ds = tf.data.Dataset.from_tensor_slices((part.path.tolist(), [labels.index(x) for x in part.label]))
        def decode(path, label):
            image = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
            image.set_shape([None, None, 3])
            return tf.image.resize(tf.cast(image, tf.float32), (224,224)) / 127.5 - 1, label
        ds = ds.map(decode)
        if split == 'train': ds = ds.shuffle(len(part), seed=42)
        return ds.batch(32).prefetch(tf.data.AUTOTUNE)
    train, val, test = [dataset(s) for s in ['train','validation','test']]
    base = tf.keras.applications.MobileNetV2(include_top=False, weights='imagenet', input_shape=(224,224,3))
    base.trainable = False
    inputs = tf.keras.Input((224,224,3))
    x = tf.keras.layers.RandomFlip('horizontal')(inputs)
    x = tf.keras.layers.RandomRotation(.08)(x)
    x = base(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    outputs = tf.keras.layers.Dense(len(labels), activation='softmax')(x)
    model = tf.keras.Model(inputs, outputs)
    def fit(lr, epochs):
        model.compile(optimizer=tf.keras.optimizers.Adam(lr), loss='sparse_categorical_crossentropy', metrics=['accuracy'])
        return model.fit(train, validation_data=val, epochs=epochs, callbacks=[
            tf.keras.callbacks.EarlyStopping(patience=4, restore_best_weights=True),
            tf.keras.callbacks.ModelCheckpoint(str(out/'disease.keras'), save_best_only=True)])
    warm = fit(.001, 10)
    warm_loss = min(warm.history['val_loss'])
    warm_path = out/'disease-warm.keras'; model.save(warm_path)
    base.trainable = True
    for layer in base.layers[:-20]: layer.trainable = False
    fine = fit(.00001, 20)
    if min(fine.history['val_loss']) >= warm_loss:
        model = tf.keras.models.load_model(warm_path)
    else:
        model = tf.keras.models.load_model(out/'disease.keras')
    model.save(out/'disease.keras')
    truth = np.concatenate([y.numpy() for _, y in test])
    def evaluate(candidate):
        predicted = candidate.predict(test).argmax(axis=1)
        return {'accuracy': accuracy_score(truth,predicted), 'report': classification_report(truth,predicted,labels=list(range(len(labels))),target_names=labels,output_dict=True,zero_division=0), 'confusionMatrix': confusion_matrix(truth,predicted,labels=list(range(len(labels)))).tolist()}
    metrics = {'fineTuned': evaluate(model), 'original': None, 'fieldEvaluation': 'pending'}
    plt.figure(figsize=(16,14))
    plt.imshow(metrics['fineTuned']['confusionMatrix'],cmap='Blues')
    plt.xticks(range(len(labels)),labels,rotation=90,fontsize=6)
    plt.yticks(range(len(labels)),labels,fontsize=6)
    plt.xlabel('Predicted');plt.ylabel('Actual');plt.tight_layout()
    plt.savefig(out/'disease-confusion-matrix.png');plt.close()
    if args.baseline:
        original = tf.keras.models.load_model(args.baseline, compile=False)
        if original.output_shape[-1] != len(labels): raise ValueError('Baseline labels incompatible')
        metrics['original'] = evaluate(original)
    for metric in ['accuracy','loss']:
        plt.figure()
        for key in [metric,'val_'+metric]: plt.plot(warm.history[key]+fine.history[key],label=key)
        plt.legend(); plt.savefig(out/f'disease-{metric}.png'); plt.close()
    (out/'disease-evaluation.json').write_text(json.dumps(metrics,indent=2))
    meta = {'file':'disease.keras','version':'mobilenetv2-finetuned-seed42','labels':labels,'preprocessing':'rgb_mobilenet_v2',
            'license':args.license,'sha256':hashlib.sha256((out/'disease.keras').read_bytes()).hexdigest(),
            'metrics':metrics,'configuration':{'seed':42,'batch':32,'warmEpochs':len(warm.epoch),'fineEpochs':len(fine.epoch),'manifestSha256':hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()}}
    (out/'disease.json').write_text(json.dumps(meta,indent=2))

if __name__ == '__main__': main()
