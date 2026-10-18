"""Colab/local MobileNetV2 training on reviewed ORIGINAL images only.
Run --audit-only first; review contact sheets and audit.json before --reviewed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import time
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from sklearn.model_selection import train_test_split

def audit(root, output):
    rows, rejected, hashes = [], [], []
    for path in sorted(root.glob('*/*')):
        if not path.is_file():
            continue
        try:
            with Image.open(path) as im:
                im.load()
                if min(im.size) < 64:
                    raise ValueError('Below 64 pixels')
                gray = np.asarray(ImageOps.grayscale(im).resize((9, 8)))
                bits = (gray[:, 1:] > gray[:, :-1]).flatten()
                digest = sum(int(b) << i for i, b in enumerate(bits))
                pixel_hash = hashlib.sha256(im.convert('RGB').tobytes()).hexdigest()
            rows.append({'path': str(path), 'label': path.parent.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'pixelHash': pixel_hash})
            hashes.append(digest)
        except Exception as exc:
            rejected.append({'path': str(path), 'reason': str(exc)})
    # Connected components: all dHash neighbors (distance <=6) stay together.
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(rows)):
        for j in range(i):
            if rows[i]['pixelHash'] == rows[j]['pixelHash'] or (hashes[i] ^ hashes[j]).bit_count() <= 6:
                parent[find(i)] = find(j)
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)
    conflicts = [g for g in groups.values() if len({r['label'] for r in g}) > 1]
    # Conservatively retain one representative per near-duplicate component.
    unique = [group[0] for group in groups.values() if len({r['label'] for r in group}) == 1]
    counts = dict(Counter(row['label'] for row in unique))
    report = {'images': len(rows), 'retained': len(unique), 'nearDuplicateImagesRemoved': len(rows)-len(unique),
              'classCounts': counts, 'rejected': rejected, 'conflictingGroups': conflicts,
              'nearDuplicateMethod': 'Connected components of 64-bit dHash Hamming distance <=6; one representative retained. Manual review still required.'}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    # Review every retained image, not only a sample; sheets are saved in ignored data.
    for start in range(0, len(unique), 80):
        sheet = Image.new('RGB', (800, 1000), 'white')
        draw = ImageDraw.Draw(sheet)
        for offset, row in enumerate(unique[start:start+80]):
            with Image.open(row['path']) as im:
                thumb = ImageOps.fit(im.convert('RGB'), (100, 80))
            x, y = (offset % 8)*100, (offset//8)*100
            sheet.paste(thumb, (x,y))
            draw.text((x,y+80), f'{start+offset}: {row["label"][:12]}', fill='black')
        sheet.save(output / f'review-{start//80:03}.jpg')
    return unique, report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset', type=Path, help='Reviewed original class folders')
    parser.add_argument('--output', type=Path, default=Path('data/soil-training'))
    parser.add_argument('--audit-only', action='store_true')
    parser.add_argument('--reviewed', action='store_true')
    parser.add_argument('--noncommercial-research', action='store_true')
    args = parser.parse_args()
    if not args.noncommercial_research:
        parser.error('Selected dataset is CC-BY-NC-4.0: use only after confirming noncommercial research rights.')
    rows, report = audit(args.dataset.resolve(), args.output)
    if args.audit_only:
        return
    if not args.reviewed or report['conflictingGroups']:
        parser.error('Review all contact sheets, rejected images and conflicts before training; supply --reviewed afterward.')
    if not rows or min(report['classCounts'].values()) < 10:
        parser.error('Need at least 10 independent images in every class')
    import tensorflow as tf
    from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
    tf.keras.utils.set_random_seed(42)
    started = time.time()
    labels = sorted(report['classCounts'])
    train, holdout = train_test_split(rows, test_size=.3, random_state=42, stratify=[r['label'] for r in rows])
    valid, test = train_test_split(holdout, test_size=.5, random_state=42, stratify=[r['label'] for r in holdout])
    (args.output / 'splits.json').write_text(json.dumps({'train': train, 'validation': valid, 'test': test}, indent=2))
    def dataset(items, training=False):
        def load(path, label):
            raw = tf.io.read_file(path)
            image = tf.io.decode_image(raw, channels=3, expand_animations=False)
            image.set_shape([None,None,3])
            image = tf.image.resize(image, [224,224])
            return tf.keras.applications.mobilenet_v2.preprocess_input(image), label
        ds = tf.data.Dataset.from_tensor_slices(([r['path'] for r in items], [labels.index(r['label']) for r in items]))
        if training:
            ds = ds.shuffle(len(items),seed=42)
        return ds.map(load).batch(32).prefetch(tf.data.AUTOTUNE)
    base = tf.keras.applications.MobileNetV2(weights='imagenet', include_top=False, input_shape=(224,224,3))
    base.trainable = False
    inputs = tf.keras.Input((224,224,3))
    augmented = tf.keras.Sequential([tf.keras.layers.RandomFlip('horizontal_and_vertical'), tf.keras.layers.RandomRotation(.1), tf.keras.layers.RandomZoom(.1)])(inputs)
    x = base(augmented, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(.3)(x)
    model = tf.keras.Model(inputs, tf.keras.layers.Dense(len(labels), activation='softmax')(x))
    best = args.output / 'soil-finetuned.keras'
    # Reuse checkpoint across both stages so the global best validation loss wins.
    checkpoint = tf.keras.callbacks.ModelCheckpoint(str(best), save_best_only=True, monitor='val_loss')
    def fit(epochs, rate):
        model.compile(optimizer=tf.keras.optimizers.Adam(rate), loss='sparse_categorical_crossentropy', metrics=['accuracy'])
        counts = Counter(r['label'] for r in train)
        return model.fit(dataset(train,True), validation_data=dataset(valid), epochs=epochs,
                         class_weight={i:len(train)/(len(labels)*counts[label]) for i,label in enumerate(labels)},
                         callbacks=[checkpoint, tf.keras.callbacks.EarlyStopping(patience=4,restore_best_weights=True)])
    first = fit(15,1e-3)
    model.load_weights(best)
    base.trainable = True
    for layer in base.layers[:-30]:
        layer.trainable = False
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
    second = fit(20,1e-5)
    model = tf.keras.models.load_model(best)
    pred = model.predict(dataset(test)).argmax(axis=1)
    truth = [labels.index(r['label']) for r in test]
    report.update({'labels': labels, 'splitSizes': {'train':len(train),'validation':len(valid),'test':len(test)},
                   'epochsExecuted':len(first.epoch)+len(second.epoch), 'hardware':platform.platform(),
                   'devices':[str(device) for device in tf.config.list_physical_devices()], 'seconds':time.time()-started,
                   'accuracy':accuracy_score(truth,pred), 'macroF1':f1_score(truth,pred,average='macro'),
                   'perClass':classification_report(truth,pred,labels=list(range(len(labels))),target_names=labels,output_dict=True,zero_division=0),
                   'confusionMatrix':confusion_matrix(truth,pred,labels=list(range(len(labels)))).tolist()})
    (args.output / 'evaluation.json').write_text(json.dumps(report,indent=2))
    (args.output / 'soil.json').write_text(json.dumps({'version':'mobilenet-v2-finetuned-42','file':best.name,'preprocessing':'rgb_mobilenet_v2','labels':labels,'license':'CC-BY-NC-4.0'},indent=2))

if __name__ == '__main__':
    main()
