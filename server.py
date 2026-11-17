#!/usr/bin/env python3
"""Local-only UI server. All mechanics remain in kneelab/ and work offline."""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from kneelab.api import dispatch, GET_PATHS, POST_PATHS

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
        if path in GET_PATHS:return self.reply(200,dispatch(path))
        if path in ("/","/index.html"):file=ROOT/"static/index.html"
        elif path in ("/runtime.js","/app.js","/analysis.js","/style.css","/guide.html","/chain.html","/chain.js","/chain.css","/chain-guide.html"):file=ROOT/"static"/path[1:]
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
            if not isinstance(data,dict):raise ValueError("Request body must be an object.")
            path=urlparse(self.path).path
            if path not in POST_PATHS:return self.reply(404,{"error":"Not found."})
            result=dispatch(path,data)
            if path.endswith(".csv"):
                filename="chain-cycle.csv" if path=="/api/chain/cycle.csv" else path.rsplit("/",1)[-1]
                return self.reply(200,result,"text/csv; charset=utf-8",filename)
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
