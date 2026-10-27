# -*- coding: utf-8 -*-
"""Photoroom 2API demo server — OpenAI 风格网关 + 原生透传
协议来源: Photoroom v2026.37.01 (apkdaddy 破解版) 逆向还原
"""
import base64, io, json, os, sys, time, uuid, threading, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

PORT = int(os.environ.get("PORT", "8908"))
API_KEY = os.environ.get("DEMO_KEY", "sk-photoroom-demo")
KEY_FILE = os.path.join(os.path.dirname(__file__), "anon_token.json")

FB_KEY = "AIzaSyAJGrgbFGB_-h8V2oJLr4b-_ipetqM0duU"
FB_HEADERS = {"X-Android-Package": "com.photoroom.app",
              "X-Android-Cert": "0424A4898A4B33940D8BF16E44251B876E97F8D0"}
SEG_BASE = "https://segmentation-inference.photoroom.com"
SRV_BASE = "https://serverless-api.photoroom.com"
DIF_BASE = "https://diffusion-backend.photoroom.com"

# ---------------- token 管理 ----------------
_tok_lock = threading.Lock()
_token = {"idToken": None, "refreshToken": None, "localId": None, "exp": 0}

def _load_token():
    if os.path.exists(KEY_FILE):
        d = json.load(open(KEY_FILE))
        _token.update({"idToken": d.get("idToken"), "refreshToken": d.get("refreshToken"),
                       "localId": d.get("localId"), "exp": d.get("exp", 0)})

def _save_token():
    json.dump(_token, open(KEY_FILE, "w"))

def _http(url, method="GET", headers=None, data=None, timeout=120):
    req = Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read()

def _http_err(url, method="GET", headers=None, data=None, timeout=120):
    req = Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except Exception as e:
        try:
            body = e.read()
            return getattr(e, "code", 500), {}, body
        except Exception:
            return 500, {}, str(e).encode()

def _register_anon():
    body = json.dumps({"returnSecureToken": True}).encode()
    st, _, b = _http(f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FB_KEY}",
                     "POST", {**FB_HEADERS, "Content-Type": "application/json"}, body)
    d = json.loads(b)
    if st != 200:
        raise RuntimeError(f"register failed: {b[:200]}")
    _token.update({"idToken": d["idToken"], "refreshToken": d["refreshToken"],
                   "localId": d["localId"], "exp": time.time() + 3300})
    _save_token()
    return _token

def _refresh():
    body = f"grant_type=refresh_token&refresh_token={_token['refreshToken']}".encode()
    st, _, b = _http(f"https://securetoken.googleapis.com/v1/token?key={FB_KEY}",
                     "POST", {**FB_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}, body)
    d = json.loads(b)
    if st != 200:
        return _register_anon()
    _token["idToken"] = d["id_token"]
    _token["exp"] = time.time() + 3300
    _save_token()
    return _token

def get_token():
    with _tok_lock:
        if not _token["idToken"]:
            _load_token()
        if not _token["idToken"] or time.time() > _token["exp"]:
            if _token.get("refreshToken"):
                try:
                    return _refresh()
                except Exception:
                    pass
            return _register_anon()
        return _token

# ---------------- multipart helper ----------------
def build_multipart(fields, files):
    boundary = "----pr2api" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, content, ct) in files.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode())
        buf.write(content); buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return boundary, buf.getvalue()

def parse_multipart(ct, body):
    """简单 multipart 解析 → {field: bytes}, {file: (fn, bytes, ct)}"""
    import re
    m = re.search(r"boundary=([^;]+)", ct or "")
    if not m: return {}, {}
    boundary = m.group(1).strip('"').encode()
    fields, files = {}, {}
    for part in body.split(b"--" + boundary):
        part = part.strip(b"\r\n")
        if not part or part == b"--": continue
        if b"\r\n\r\n" not in part: continue
        head, _, content = part.partition(b"\r\n\r\n")
        hm = re.search(rb'name="([^"]+)"', head)
        if not hm: continue
        name = hm.group(1).decode()
        fm = re.search(rb'filename="([^"]+)"', head)
        ctm = re.search(rb'Content-Type:\s*([^\r\n]+)', head, re.I)
        if fm:
            files[name] = (fm.group(1).decode(), content, (ctm.group(1).decode() if ctm else "application/octet-stream"))
        else:
            fields[name] = content.decode("utf-8", "replace")
    return fields, files

# ---------------- demo HTML ----------------
DEMO_HTML = """<!doctype html><html lang=zh><head><meta charset=utf-8><title>Photoroom 2API Demo</title>
<style>body{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;background:#0f1115;color:#e6e6e6}
h1{color:#7c9cff}fieldset{border:1px solid #333;border-radius:8px;margin:1rem 0}
input,button,select{padding:.5rem;border-radius:6px;border:1px solid #444;background:#1a1d24;color:#eee}
button{background:#7c9cff;color:#000;font-weight:700;cursor:pointer}img{max-width:100%;border-radius:8px;margin-top:.5rem}
#out{white-space:pre-wrap;font-size:.85rem;color:#9cff9c}</style></head><body>
<h1>Photoroom 2API Demo</h1><div id=out>ready</div>
<fieldset><legend>AI 抠图 (v1/mask)</legend><input type=file id=f1 accept=image/*>
<select id=mt><option>person</option><option>object</option><option>graphics</option><option>standard</option></select>
<button onclick="job('mask')">抠图</button><br><img id=im1></fieldset>
<fieldset><legend>AI 超分 2x (v3/upscale)</legend><input type=file id=f2 accept=image/*>
<button onclick="job('upscale')">放大</button><br><img id=im2></fieldset>
<fieldset><legend>AI 擦除 (v1/erase)</legend><input type=file id=f3 accept=image/*>
<input type=file id=f3m accept=image/*> <span style=font-size:.8rem>mask(白=擦除)</span>
<button onclick="job('erase')">擦除</button><br><img id=im3></fieldset>
<fieldset><legend>AI 填充 (v1/fill)</legend><input type=file id=f4 accept=image/*>
<input type=file id=f4m accept=image/*><input id=p4 placeholder=prompt>
<button onclick="job('fill')">填充</button><br><img id=im4></fieldset>
<script>
async function job(kind){
 const out=document.getElementById('out'); out.textContent='processing...';
 const map={mask:['f1'],upscale:['f2'],erase:['f3','f3m'],fill:['f4','f4m']};
 const fd=new FormData();
 for(const id of map[kind]){const el=document.getElementById(id);if(el.files[0])fd.append(id,el.files[0]);}
 if(kind==='fill')fd.append('prompt',document.getElementById('p4').value);
 if(kind==='mask')fd.append('model_type',document.getElementById('mt').value);
 try{
  const r=await fetch('/api/'+kind,{method:'POST',body:fd});
  const b=await r.blob();
  if(!r.ok){out.textContent='ERR '+r.status+' '+(await b.text()).slice(0,300);return}
  const url=URL.createObjectURL(b);
  document.getElementById('im'+ (kind==='mask'?1:kind==='upscale'?2:kind==='erase'?3:4)).src=url;
  out.textContent='OK '+r.status+' '+(b.type)+' '+(b.size>>10)+'KB';
 }catch(e){out.textContent='ERR '+e}
}
</script></body></html>"""

# ---------------- handler ----------------
class H(BaseHTTPRequestHandler):
    server_version = "PR2API/1.0"
    def log_message(self, fmt, *a):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % a))

    def _send(self, code, body, ct="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _auth(self):
        return self.headers.get("Authorization", "") == f"Bearer {API_KEY}"

    def do_GET(self):
        if self.path == "/":
            return self._send(200, DEMO_HTML.encode(), "text/html; charset=utf-8")
        if self.path == "/health":
            t = get_token()
            return self._json(200, {"status": "ok", "uid": t["localId"],
                                    "token_exp_in": int(t["exp"] - time.time())})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path in ("/health",): return self.do_GET()
        if not self._auth():
            return self._json(401, {"error": {"message": "use Authorization: Bearer " + API_KEY}})
        ln = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(ln) if ln else b""
        try:
            if self.path == "/api/mask": return self._mask(body)
            if self.path == "/api/upscale": return self._upscale(body)
            if self.path == "/api/erase": return self._erase(body)
            if self.path == "/api/fill": return self._fill(body)
            if self.path == "/v1/images/edits": return self._openai_edits(body)
            return self._json(404, {"error": {"message": "unknown endpoint"}})
        except Exception as e:
            return self._json(502, {"error": {"message": str(e)}})

    def _up_image(self, body, fid="image"):
        fields, files = parse_multipart(self.headers.get("Content-Type", ""), body)
        cand = files.get(fid) or files.get("sourceImage") or files.get("imageFile")
        if not cand:
            for v in files.values():
                if v[2].startswith("image/"): cand = v; break
        if not cand: raise ValueError("no image file in request")
        fields_out = {k: v for k, v in fields.items() if k not in ("image", fid, "sourceImage", "imageFile")}
        return cand[1], fields_out

    def _tok_hdr(self):
        t = get_token()
        return {"Authorization": t["idToken"], "pr-app-version": "2026.37.01 (2546)"}

    def _mask(self, body):
        img, f = self._up_image(body, "image")
        fields, _ = parse_multipart(self.headers.get("Content-Type", ""), body)
        mt = fields.get("model_type", "person")
        bnd, mp = build_multipart(
            {"user_id": get_token()["localId"], "resize_mask": "false",
             "model_type": mt, "experiment_flag": "default"},
            {"sourceImage": ("sourceImage.jpg", img, "image/jpeg")})
        st, _, resp = _http_err(f"{SEG_BASE}/v1/mask", "POST",
                                {**self._tok_hdr(), "Content-Type": f"multipart/form-data; boundary={bnd}",
                                 "pr-feature-name": "remove_background"}, mp)
        if st != 200: return self._json(st, {"upstream": json.loads(resp or b"{}")})
        return self._send(200, base64.b64decode(json.loads(resp)["b64_mask"]), "image/png")

    def _upscale(self, body):
        img, _ = self._up_image(body, "image")
        bnd, mp = build_multipart({"outputFormat": "png"},
                                  {"imageFile": ("sourceImage.jpg", img, "image/jpeg")})
        st, _, resp = _http_err(f"{SRV_BASE}/v3/upscale", "POST",
                                {**self._tok_hdr(), "Content-Type": f"multipart/form-data; boundary={bnd}"}, mp, 180)
        if st != 200: return self._json(st, {"upstream": resp.decode("utf-8", "replace")[:400]})
        return self._send(200, resp, "image/png")

    def _erase(self, body):
        _, files = parse_multipart(self.headers.get("Content-Type", ""), body)
        img = files["image"][1] if "image" in files else (files["imageFile"][1] if "imageFile" in files else None)
        mask = files["mask"][1] if "mask" in files else (files["maskFile"][1] if "maskFile" in files else None)
        if not img or not mask: return self._json(400, {"error": {"message": "need image + mask files"}})
        bnd, mp = build_multipart({}, {"imageFile": ("s.jpg", img, "image/jpeg"),
                                       "maskFile": ("m.png", mask, "image/png")})
        st, _, resp = _http_err(f"{DIF_BASE}/v1/erase", "POST",
                                {**self._tok_hdr(), "Content-Type": f"multipart/form-data; boundary={bnd}"}, mp, 180)
        if st != 200: return self._json(st, {"upstream": resp.decode("utf-8", "replace")[:400]})
        return self._send(200, resp, "image/png")

    def _fill(self, body):
        fields, files = parse_multipart(self.headers.get("Content-Type", ""), body)
        img = files["image"][1] if "image" in files else (files["imageFile"][1] if "imageFile" in files else None)
        mask = files["mask"][1] if "mask" in files else (files["maskFile"][1] if "maskFile" in files else None)
        prompt = fields.get("prompt", "")
        if not img or not mask: return self._json(400, {"error": {"message": "need image + mask + prompt"}})
        bnd, mp = build_multipart({"prompt": prompt, "seed": "0"},
                                  {"imageFile": ("s.jpg", img, "image/jpeg"),
                                   "maskFile": ("m.png", mask, "image/png")})
        st, _, resp = _http_err(f"{DIF_BASE}/v1/fill", "POST",
                                {**self._tok_hdr(), "Content-Type": f"multipart/form-data; boundary={bnd}"}, mp, 180)
        if st != 200: return self._json(st, {"upstream": resp.decode("utf-8", "replace")[:400]})
        return self._send(200, resp, "image/jpeg")

    def _openai_edits(self, body):
        """OpenAI 兼容: /v1/images/edits → 抠图合成透明底 PNG"""
        import time as _t
        img, fields = self._up_image(body, "image")
        mt = fields.get("model", "person")
        bnd, mp = build_multipart(
            {"user_id": get_token()["localId"], "resize_mask": "false",
             "model_type": mt, "experiment_flag": "default"},
            {"sourceImage": ("sourceImage.jpg", img, "image/jpeg")})
        st, _, resp = _http_err(f"{SEG_BASE}/v1/mask", "POST",
                                {**self._tok_hdr(), "Content-Type": f"multipart/form-data; boundary={bnd}",
                                 "pr-feature-name": "remove_background"}, mp)
        if st != 200: return self._json(st, {"error": {"message": resp.decode('utf-8', 'replace')[:300]}})
        mask = base64.b64decode(json.loads(resp)["b64_mask"])
        from PIL import Image
        src = Image.open(io.BytesIO(img)).convert("RGBA")
        m = Image.open(io.BytesIO(mask)).convert("L").resize(src.size)
        src.putalpha(m)
        ob = io.BytesIO(); src.save(ob, "PNG")
        b64 = base64.b64encode(ob.getvalue()).decode()
        self._json(200, {"created": int(_t.time()), "data": [{"b64_json": b64}]})

if __name__ == "__main__":
    _load_token()
    print(f"Photoroom 2API demo on :{PORT}  key={API_KEY}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
