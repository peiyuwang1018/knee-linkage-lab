#!/usr/bin/env python3
"""Start or reuse this local app without installing dependencies."""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser();p.add_argument("--no-open",action="store_true")
    p.add_argument("--port",type=int,default=8786);a=p.parse_args()
    url=f"http://127.0.0.1:{a.port}"
    def alive():
        try:
            with urllib.request.urlopen(url+"/api/health",timeout=.5) as r:
                return json.load(r).get("app")=="knee-linkage-lab"
        except Exception:return False
    if not alive():
        (ROOT/"output").mkdir(exist_ok=True)
        with (ROOT/"output/server.log").open("a") as log:
            proc=subprocess.Popen([sys.executable,str(ROOT/"server.py"),"--port",str(a.port)],
                                  cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
        for _ in range(40):
            if alive():break
            if proc.poll() is not None:
                raise SystemExit("Server could not start; see output/server.log. Try --port 8787 if 8786 is occupied.")
            time.sleep(.1)
        else:raise SystemExit("Server did not start; see output/server.log.")
    print(url)
    if not a.no_open:webbrowser.open(url)


if __name__=="__main__":main()
