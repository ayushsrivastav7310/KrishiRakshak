"""Package the standalone training script in a reproducible Colab notebook."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
def markdown(text):
    return {'cell_type':'markdown','metadata':{},'source':text.splitlines(True)}
def code(text):
    return {'cell_type':'code','metadata':{},'source':text.splitlines(True),'execution_count':None,'outputs':[]}
script = (root/'backend/ml/train_soil.py').read_text(encoding='utf-8')
cells = [markdown('''# Phase 2 — MobileNetV2 soil fine-tuning (pending)
This notebook has not been executed. Select a Colab GPU runtime.

Dataset: [Phantom-fs original images](https://github.com/Phantom-fs/Soil-Classification-Dataset), **CC-BY-NC-4.0**. Noncommercial research/educational use only; secure separate permission before commercial use. Attribution: Farhan Sheth, Priya Mathur, Amit Kumar Gupta, Sandeep Chaurasia, Engineering Applications of Artificial Intelligence 158 (2025), 111425, DOI 10.1016/j.engappai.2025.111425.

The seven classes stay distinct: Alluvial, Arid, Black, Laterite, Mountain, Red, Yellow Soil. There is no mapping to the pretrained model's three classes or farm texture labels. Use original images only; exclude CyAUG and all derived images. The audit removes detected duplicate/near-duplicate groups before a stratified 70/15/15 split. Review every contact sheet, reject poor images, and resolve label conflicts before training. Perceptual hashing cannot guarantee detection of every related image; visually inspect split membership as well.
'''), code('%pip install tensorflow==2.21.0 scikit-learn==1.9.1 pillow==12.3.0 numpy==2.5.4'),
code('''# Confirm you have rights to use these images for this run.
NONCOMMERCIAL_RESEARCH = False
assert NONCOMMERCIAL_RESEARCH, "Review the dataset license before downloading."
import subprocess
subprocess.run(["git", "clone", "https://github.com/Phantom-fs/Soil-Classification-Dataset.git", "/content/soil-data"], check=True)
print(subprocess.check_output(["git", "-C", "/content/soil-data", "rev-parse", "HEAD"]).decode())
# Record this revision alongside evaluation.json for reproducibility.
'''), code('%%writefile /content/train_soil.py\n'+script),
code('''from pathlib import Path
DATASET = Path('/content/soil-data/Orignal-Dataset')
print(list(DATASET.iterdir()))
# Point DATASET to the directory whose immediate subfolders are the seven original classes.
'''), code('!python /content/train_soil.py "{DATASET}" --output /content/soil-run --noncommercial-research --audit-only'),
markdown('Inspect audit.json and every review-*.jpg contact sheet in the Colab file browser. Remove bad images, resolve cross-label duplicate conflicts, and rerun the audit. Do not assert review without performing it. The file list and hashes in splits.json document the final split. Training and validation augmentation are separated; test images never affect model selection.'),
code('''REVIEW_COMPLETE = False
assert REVIEW_COMPLETE, "Finish the visual and label audit first."
!python /content/train_soil.py "{DATASET}" --output /content/soil-run --noncommercial-research --reviewed
'''), code('''import json
print(json.dumps(json.load(open('/content/soil-run/evaluation.json')), indent=2))
'''), markdown('Download soil-finetuned.keras, soil.json, audit.json, splits.json and evaluation.json. Keep the full dataset revision and dependency versions. For a separately reviewed noncommercial deployment, copy the model and its metadata to backend/artifacts and restart FastAPI. This replaces the three-class classifier with a separately labeled seven-class model; never silently merge labels. Evaluation reports include actual image counts, hardware, executed epochs, precision, recall, F1 and confusion matrix. No accuracy is claimed until this notebook completes.')]
for index, cell in enumerate(cells):
    cell['id'] = f'cell-{index}'
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'colab':{'name':'Phase_2_Soil_Training.ipynb'},'accelerator':'GPU'},'cells':cells}
(root/'backend/ml/Phase_2_Soil_Training.ipynb').write_text(json.dumps(notebook,indent=2),encoding='utf-8')
