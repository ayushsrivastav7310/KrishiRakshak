"""Generate a portable Colab notebook embedding the exact local training source."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/'backend/ml/train_disease.py').read_text()
def cell(kind,text):
    return {'cell_type':kind,'metadata':{},'source':text.splitlines(True),**({'execution_count':None,'outputs':[]} if kind=='code' else {})}
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'Phase 3 Disease Training'},'accelerator':'GPU','kernelspec':{'name':'python3','display_name':'Python 3'}},'cells':[
    cell('markdown','# Phase 3 — MobileNetV2 training and evaluation\nTraining has NOT been executed. Choose a GPU runtime. This notebook embeds the repository training pipeline.\n\nUse PlantVillage color images only (mohanty/PlantVillage card: CC-BY-SA-3.0). Preserve attribution/share-alike obligations. Do not mix grayscale/segmented versions. Prepare a CSV with path,label,leaf_group,split. Use official leaf-grouped test membership and split remaining training leaf groups for validation. Keep all exact and near duplicates in one split. The pipeline audits this and aborts on leakage. Do not tune on test results.\n\nStore images and manifest in Google Drive. Paths in the manifest are relative to the manifest folder. If no official split is usable, partition leaf groups with seed 42 into 70/15/15 and record this decision.\n'),
    cell('code','%pip install tensorflow==2.21.0 pandas scikit-learn matplotlib pillow ImageHash\n'),
    cell('code','from google.colab import drive\ndrive.mount("/content/drive")\n'),
    cell('code','from pathlib import Path\nPath("/content/train_disease.py").write_text('+repr(source)+')\n'),
    cell('code','MANIFEST = "/content/drive/MyDrive/PlantVillage/manifest.csv"\nOUTPUT = "/content/drive/MyDrive/AgriSmart-disease-artifacts"\nassert Path(MANIFEST).is_file(), "Prepare the licensed, leaf-grouped manifest first"\n'),
    cell('code','import subprocess, sys\nsubprocess.run([sys.executable,"/content/train_disease.py",MANIFEST,"--license","CC-BY-SA-3.0; PlantVillage, Mohanty et al. 2016","--output",OUTPUT],check=True)\n'),
    cell('code','import json\nfrom IPython.display import display, Image\nprint(Path(OUTPUT,"disease-evaluation.json").read_text())\nfor metric in ["accuracy","loss"]: display(Image(filename=str(Path(OUTPUT,f"disease-{metric}.png"))))\n'),
    cell('markdown','## Comparison and deployment\nThe runtime initial model uses Transformers/PyTorch with its bundled resize/crop processor. The fine-tuned artifact here uses Keras and RGB MobileNetV2 normalization. A same-dataset comparison must use each model\'s documented processor and identical held-out image IDs. Do not pass the Transformers safetensors file to --baseline (that option is for compatible Keras artifacts only). Independent field evaluation remains pending until appropriately licensed labeled photographs are available. Copy disease.keras and disease.json into backend/artifacts after inspecting the report.\n')
]}
(root/'backend/ml/Phase_3_Disease_Training.ipynb').write_text(json.dumps(notebook,indent=2))
print('Generated Phase_3_Disease_Training.ipynb')
