"""Download only pinned safetensors/config files, never remote executable code."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

REPO='neghani/plantvillage-mobilenetv2'
REVISION='d33601185b32cf05b3942661b8d84ffb86dc48ec'
FILES=['config.json','preprocessor_config.json','model.safetensors','README.md','calibration.json','threshold.json']

def main():
    root=Path(__file__).resolve().parents[1]/'artifacts'
    folder=root/'disease-hf';folder.mkdir(parents=True,exist_ok=True)
    checksums={}
    for filename in FILES:
        with urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{filename}',timeout=60) as response:
            content=response.read(32*1024*1024)
        (folder/filename).write_bytes(content)
        checksums[filename]=hashlib.sha256(content).hexdigest()
    config=json.loads((folder/'config.json').read_text())
    meta={'framework':'transformers','version':REVISION,'source':f'https://huggingface.co/{REPO}/tree/{REVISION}',
          'license':'Apache-2.0 (publisher model card)','labels':[config['id2label'][str(i)] for i in range(len(config['id2label']))],
          'checksums':checksums,'preprocessing':'bundled MobileNetV2ImageProcessor: shortest edge 256, center crop 224, RGB rescale and normalize',
          'metrics':None,'evaluationStatus':'Local held-out evaluation pending; upstream model card reports are not local validation.',
          'limitations':'Closed-set 38-class classifier; not validated for field diagnosis. Upstream card warns about same-leaf leakage and poor field performance.'}
    (root/'disease.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps({'version':REVISION,'classes':len(meta['labels']),'checksums':checksums},indent=2))

if __name__=='__main__':main()
