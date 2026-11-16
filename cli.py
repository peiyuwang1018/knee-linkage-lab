#!/usr/bin/env python3
"""Reproducible analysis outside the UI."""
import argparse
import json
from pathlib import Path
from kneelab.model import Config,cycle
from kneelab.scan import scan
from kneelab.export import cycle_csv,scan_csv


def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=["cycle","scan"])
    p.add_argument("--config",type=Path);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();config=json.loads(a.config.read_text()) if a.config else Config().to_dict()
    config=config.get("config",config)  # UI snapshots also preserve display / capacity settings.
    result=cycle(config) if a.mode=="cycle" else scan(config)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.with_suffix(".json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    a.out.with_suffix(".csv").write_text(cycle_csv(result) if a.mode=="cycle" else scan_csv(result),encoding="utf-8")
    print(json.dumps(result["summary"] if a.mode=="cycle" else {k:v for k,v in result.items() if k!="candidates"},indent=2))


if __name__=="__main__":main()
