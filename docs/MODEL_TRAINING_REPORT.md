# Disease model training and evaluation report

Status: original model integrated and real inference executed; fine-tuning and independent held-out evaluation PENDING. No model was trained and no local accuracy, precision, recall or F1 is claimed.

The requested candidate is compatible through an added CPU PyTorch/Transformers adapter, so no substitute was chosen. Original weights are revision `d33601185b32cf05b3942661b8d84ffb86dc48ec`, 38 classes. Publisher metrics were inspected but are not project evaluation results. The card acknowledges same-leaf leakage and very poor results on a small field/web-photo set, with conflicting sections across evaluation versions. This prevents treating its lab accuracy as field accuracy.

Reproducible Keras MobileNetV2 pipeline is supplied for a separately trained candidate, retaining the existing backend's TensorFlow capabilities. Colab notebook embeds the pipeline, mounts Drive, installs dependencies, trains and displays actual resulting reports. Generate again after source edits using `python scripts/make_disease_notebook.py`.

## Data preparation contract

Use licensed PlantVillage color images and official leaf grouping. The upstream repository documents an existing leaf-respecting 80/20 split: retain its test membership and derive validation using training leaf groups only. Where no suitable split exists, use a deterministic 70/15/15 leaf-grouped partition. Manifest CSV: `path,label,leaf_group,split`, with split train/validation/test. Image paths relative to the manifest, labels exact PlantVillage names. Preparing this full manifest and downloading the full dataset are pending; the notebook requires that input rather than inventing group identities.

Preparation decodes every image, records corrupted paths, reports per-split/class counts, removes same-split exact duplicates and aborts on cross-split exact/near duplicates or label conflicts. Perceptual hash distance ≤4 across splits triggers regrouping; exhaustive pair checks may be slow for the full dataset. Leaf-group cross-split overlap aborts. Auditing a hand-supplied manifest cannot prove the source leaf grouping was correct; source membership must be reviewed.

## Training configuration

- Seed 42, deterministic TensorFlow operations, batch 32, 224×224 RGB MobileNetV2 preprocessing.
- ImageNet initialization; freeze backbone, up to 10 head-training epochs at 1e-3.
- Fine-tune last 20 backbone layers, up to 20 epochs at 1e-5; backbone batch normalization held in inference mode.
- Training-only random flips/rotations. Validation/test deterministic.
- Early stopping patience 4 and best-validation checkpoints. Retain warm-start checkpoint if fine-tuning worsens validation loss.
- Untouched test evaluated after selection. Output class report includes precision/recall/macro and weighted F1, test accuracy, confusion matrix JSON/PNG, accuracy/loss PNGs, split manifest, data audit, checksum/version/config metadata.

Install `backend/requirements-disease.txt` then run `backend/ml/train_disease.py manifest.csv --license "CC-BY-SA-3.0; attribution" --output <candidate-dir>`. No checkpoints or datasets are committed.

`backend/ml/evaluate_disease.py manifest.csv --original backend/artifacts --candidate <candidate-dir> --output comparison.json` compares exact same held-out IDs using each model's processor and compatible label sets. The original artifact must reside outside candidate output. This evaluation has not been run; independent licensed field photographs are also pending. The single public-image smoke may overlap pretraining and is not an accuracy estimate.
