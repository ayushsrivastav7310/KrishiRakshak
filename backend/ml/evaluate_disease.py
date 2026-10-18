"""Compare installed original/fine-tuned models on identical untouched test IDs."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.diseases import DiseaseModel

def main():
    import pandas as pd
    from PIL import Image
    from sklearn.metrics import classification_report,confusion_matrix,accuracy_score
    p=argparse.ArgumentParser()
    p.add_argument('manifest');p.add_argument('--original',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output',required=True)
    a=p.parse_args(); frame=pd.read_csv(a.manifest)
    if frame.groupby('leaf_group').split.nunique().max()!=1: raise ValueError('Leaf leakage')
    test=frame[frame.split=='test']
    if test.empty:raise ValueError('No held-out test images')
    original,candidate=DiseaseModel(a.original),DiseaseModel(a.candidate)
    original.load();candidate.load()
    labels=original.meta['labels']
    if set(labels)!=set(candidate.meta['labels']):raise ValueError('Incompatible class sets')
    truth=test.label.tolist()
    result={'manifestSha256':hashlib.sha256(Path(a.manifest).read_bytes()).hexdigest(),'testImages':len(test),'models':{}}
    for name,model in [('original',original),('fineTuned',candidate)]:
        predictions=[]
        for row in test.to_dict('records'):
            with Image.open(Path(a.manifest).resolve().parent/row['path']) as im:
                predictions.append(model.predict(im.convert('RGB'),row['label'].split('___')[0])['label'])
        result['models'][name]={'version':model.meta['version'],'accuracy':accuracy_score(truth,predictions),
            'report':classification_report(truth,predictions,labels=labels,output_dict=True,zero_division=0),
            'labels':labels,'confusionMatrix':confusion_matrix(truth,predictions,labels=labels).tolist()}
    Path(a.output).write_text(json.dumps(result,indent=2))

if __name__=='__main__':main()
