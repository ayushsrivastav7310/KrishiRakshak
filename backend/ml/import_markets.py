"""Operator-only import of downloaded official CSVs; not a public write API."""
import argparse
import csv
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.database import Database
from app.phase_store import migrate
from app.mandi import ingest,import_msp

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('csv'); p.add_argument('--database',required=True)
    p.add_argument('--msp',action='store_true')
    p.add_argument('--unit',choices=['INR/quintal','INR/kg'],default='INR/quintal')
    a=p.parse_args(); db=Database(a.database); migrate(db)
    try:
        with open(a.csv,encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        print(import_msp(db,rows) if a.msp else ingest(db,rows,unit=a.unit))
    finally: db.close()
