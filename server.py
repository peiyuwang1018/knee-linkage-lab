#!/usr/bin/env python3
"""Local-only UI server. All mechanics remain in kneelab/ and work offline."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from kneelab.model import Config,cycle
from kneelab.scan import DEFAULT_GRID,DEFAULT_LIMITS,scan
from kneelab.export import cycle_csv,scan_csv

ROOT=Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def reply(self,status,body,ctype="application/json; charset=utf-8",filename=None):
        if not isinstance(body,(str,bytes)):
            body=json.dumps(body,allow_nan=False)
        if isinstance(body,str):body=body.encode("utf-8")
        self.send_response(status);self.send_header("Content-Type",ctype)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        if filename:self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(body)

    def trusted(self):
        host=self.headers.get("Host","")
        allowed={f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}
        origin=self.headers.get("Origin")
        return host in allowed and (origin is None or origin=="http://"+host)

    def do_GET(self):
        if not self.trusted():return self.reply(403,{"error":"Local requests only."})
        path=urlparse(self.path).path
        if path=="/api/health":return self.reply(200,{"app":"knee-linkage-lab","version":"0.4.0"})
        if path=="/api/defaults":
            return self.reply(200,dict(config=Config().to_dict(),grid=DEFAULT_GRID,limits=DEFAULT_LIMITS))
        if path in ("/","/index.html"):file=ROOT/"static/index.html"
        elif path in ("/app.js","/style.css","/guide.html"):file=ROOT/"static"/path[1:]
        elif path in ("/model.md", "/findings.md", "/readme.md"):
            names = {"/model.md": "docs/Model.md", "/findings.md": "docs/Initial-findings.en.md",
                     "/readme.md": "README.md"}
            file = ROOT/names[path]
        else:return self.reply(404,{"error":"Not found."})
        ctype=mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        return self.reply(200,file.read_bytes(),ctype+("; charset=utf-8" if ctype.startswith("text/") else ""))

    def do_POST(self):
        if not self.trusted():return self.reply(403,{"error":"Local requests only."})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<=1000000:raise ValueError("Invalid request size.")
            data=json.loads(self.rfile.read(size))
            path=urlparse(self.path).path
            if path in ("/api/cycle","/api/cycle.csv"):
                result=cycle(data.get("config",{}))
                if path.endswith(".csv"):return self.reply(200,cycle_csv(result),"text/csv; charset=utf-8","cycle.csv")
            elif path in ("/api/scan","/api/scan.csv"):
                result=scan(data.get("config",{}),data.get("grid"),data.get("limits"))
                if path.endswith(".csv"):return self.reply(200,scan_csv(result),"text/csv; charset=utf-8","scan.csv")
            else:return self.reply(404,{"error":"Not found."})
            self.reply(200,result)
        except (ValueError,TypeError,KeyError,OverflowError) as e:
            self.reply(400,{"error":str(e)})

    def log_message(self,fmt,*args):
        if args and str(args[1] if len(args)>1 else "").startswith("5"):
            super().log_message(fmt,*args)


def main():
    p=argparse.ArgumentParser();p.add_argument("--port",type=int,default=8786);a=p.parse_args()
    server=ThreadingHTTPServer(("127.0.0.1",a.port),Handler)
    print(f"Knee Linkage Lab: http://127.0.0.1:{a.port}",flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=="__main__":main()
