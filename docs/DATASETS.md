# Dataset and model source audit — 18 October 2026

## Crop dataset used

[Atharva Ingle — Crop Recommendation Dataset](https://www.kaggle.com/datasets/atharvaingle/crop-recommendation-dataset), version 1. Kaggle's public dataset metadata API reports **Apache 2.0**. License evidence and the full publisher description are retained locally under ignored `backend/data/ml/crop-source.json` and `crop-description.json`. [Apache 2.0 terms](https://www.apache.org/licenses/LICENSE-2.0).

Downloaded CSV SHA-256: `54a5a6e5408668e668667efc50de2fc867c1b875e0431b4f54dd331b0a109a4e`. Actual inspection: 2,200 rows, 22 labels, 100 rows per label, no missing values, no identical feature vectors and no conflicting labels for identical features. Values pass finite/range validation. Publisher provenance describes augmented rainfall, climate and fertilizer data for India; original collection and spatial independence were not independently validated.

Publisher descriptions specify °C, relative humidity %, pH and rainfall mm. NPK are described as soil-content ratios with **no measurement units**, and rainfall has **no accumulation period**. The implementation does not invent these units or convert soil-test values. Current weather remains an explicitly labeled, editable estimate.

## Pretrained soil model used

[shrutmpatil/soil-classification-model](https://huggingface.co/shrutmpatil/soil-classification-model), MIT. Resolved revision and SHA-256 appear in `soil-model.json`; retained license notice: `SOIL_MODEL_LICENSE.txt`. Class order verified from the publisher's encoder bytes without unpickling: Medium Black Soil, Reddish Brown Soil, Saline Soil.

Important discrepancy: the model card describes MobileNetV2, but inspecting the downloaded HDF5 configuration reveals **VGG16-style convolution blocks and a flatten/dense head**. The implementation uses the requested artifact as downloaded. It follows [the publisher's file-picker inference path](https://github.com/shrutmpatil/Machine-Learning-Framework-for-Soil-Classification-and-Nutrient-Aware-Crop-Recommendation/blob/main/predict2.py): OpenCV BGR, bilinear resize to 224×224, float32 /255. This also agrees with `data_collection.py` → `data_preprocessing.py` → VGG `train_model.py`. The publisher's other paths conflict (VGG preprocessing in utils; additional normalization in MobileNet training). Exact training provenance of the uploaded weights is unverified. This uncertainty is included in metadata and soil results.

No local soil accuracy, precision, recall, F1 or confusion matrix is claimed. The brown-image smoke checks prove model execution and API integration, not soil recognition quality. Publisher-reported performance has not been adopted as a local measurement. Softmax scores are uncalibrated; no reliable open-set detector is supplied.

## Soil dataset selected for the pending research workflow

[Phantom-fs/Soil-Classification-Dataset](https://github.com/Phantom-fs/Soil-Classification-Dataset), [license file](https://github.com/Phantom-fs/Soil-Classification-Dataset/blob/main/LICENCE): **CC BY-NC 4.0**, explicitly research/educational and noncommercial. It cannot be assumed suitable for a commercial deployment. No images or fine-tuned derivative weights from this source are distributed with the application.

Seven published categories: Alluvial, Black, Laterite, Red, Yellow, Arid and Mountain Soil. They remain separate; none is mapped to the pretrained model or sandy/clay/loamy/silty texture labels. Use `Orignal-Dataset` originals; exclude `CyAUG-Dataset`. The source README reports 1,189 original images and inconsistent augmented totals; these are **publisher counts, not locally audited counts**.

The original image corpus has not been downloaded, visually reviewed or trained in this run. Quality, duplicate/near-duplicate groups, class imbalance and labeling consistency therefore remain pending. The supplied notebook/script writes actual counts, rejects small/corrupt images, identifies perceptual duplicate groups and cross-label conflicts, generates contact sheets, and requires review before training. It retains one image per detected near-duplicate component before independent train/validation/test splitting. Manual review is still required because perceptual hashing is not a complete guarantee against related-image leakage.

Attribution for future permitted use: Farhan Sheth, Priya Mathur, Amit Kumar Gupta and Sandeep Chaurasia, *An advanced artificial intelligence framework integrating ensembled convolutional neural networks and Vision Transformers for precise soil classification with adaptive fuzzy logic-based crop recommendations*, Engineering Applications of Artificial Intelligence 158 (2025), 111425. [DOI](https://doi.org/10.1016/j.engappai.2025.111425).

The other suggested Kaggle soil dataset was not selected or downloaded; no reuse permission is claimed for it.

## Weather

[Open-Meteo forecast API documentation](https://open-meteo.com/en/docs). Live request and saved response: `weather-smoke.json`. UI includes Open-Meteo attribution. Values are model-based weather estimates, not on-farm measurements. Review [Open-Meteo licensing and terms](https://open-meteo.com/en/terms) before commercial deployment; the free public endpoint's service conditions are separate from data attribution.
