# -*- coding: utf-8 -*-
"""Photoroom 2API 本地压测 — 只压自己的 demo server"""
import io, json, statistics, sys, time, base64
import concurrent.futures as cf
import urllib.request, urllib.error

BASE = "http://127.0.0.1:8908"
KEY = "sk-photoroom-demo"
sys.stdout.reconfigure(encoding="utf-8")

def req(path, data=None, headers=None, timeout=120):
    h = {"Authorization": f"Bearer {KEY}", **(headers or {})}
    r = urllib.request.Request(BASE + path, data=data, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.perf_counter() - t0

def multipart(fields, files):
    b = "----st" + str(time.time_ns())
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, c, ct) in files.items():
        buf.write(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode())
        buf.write(c); buf.write(b"\r\n")
    buf.write(f"--{b}--\r\n".encode())
    return {"Content-Type": f"multipart/form-data; boundary={b}"}, buf.getvalue()

img = open("test.jpg", "rb").read()
mask = open("mask_result.png", "rb").read()
results = []

def bench(name, n, fn, conc=10):
    times, codes = [], []
    def run():
        st, _, dt = fn()
        codes.append(st); return dt
    with cf.ThreadPoolExecutor(conc) as ex:
        times = list(ex.map(lambda _: run(), range(n)))
    ok = sum(1 for c in codes if 200 <= c < 300)
    results.append((name, n, ok, codes[:3], statistics.median(times), sorted(times)[int(len(times)*0.95)-1]))
    print(f"{name:28s} n={n:4d} ok={ok}/{n} p50={statistics.median(times)*1000:7.1f}ms p95={sorted(times)[int(len(times)*0.95)-1]*1000:7.1f}ms sample_codes={codes[:3]}")

# 1. health 轻端点
bench("health x200 c10", 200, lambda: req("/health", timeout=15), 10)
# 2. health 高并发
bench("health x60 c60", 60, lambda: req("/health", timeout=30), 60)
# 3. 真实抠图 x12 c4
hd, body = multipart({"model_type": "person"}, {"image": ("t.jpg", img, "image/jpeg")})
bench("mask x12 c4", 12, lambda: req("/api/mask", body, hd, 120), 4)
# 4. OpenAI 兼容 edits x6 c2
bench("openai-edits x6 c2", 6, lambda: req("/v1/images/edits", body, hd, 120), 2)
# 5. upscale x4 c2
hd2, body2 = multipart({}, {"image": ("t.jpg", img, "image/jpeg")})
bench("upscale x4 c2", 4, lambda: req("/api/upscale", body2, hd2, 180), 2)
# 6. erase x4 c2
hd3, body3 = multipart({}, {"image": ("t.jpg", img, "image/jpeg"), "mask": ("m.png", mask, "image/png")})
bench("erase x4 c2", 4, lambda: req("/api/erase", body3, hd3, 180), 2)
# 7. fill x4 c2
hd4, body4 = multipart({"prompt": "blue sky"}, {"image": ("t.jpg", img, "image/jpeg"), "mask": ("m.png", mask, "image/png")})
bench("fill x4 c2", 4, lambda: req("/api/fill", body4, hd4, 180), 2)
# 8. 错误路径
st, _, _ = req("/api/mask", b"", {"Content-Type": "multipart/form-data; boundary=x"}, 15)
print(f"错误路径 no-image  : {st} (期望400/502)")
st, _, _ = req("/api/upscale", body2, {}, 15)
print(f"错误路径 no-auth   : {st} (期望401)")
st, _, _ = req("/api/nothing", body2, hd2, 15)
print(f"错误路径 unknown   : {st} (期望404)")

# 汇总
print("\n==== SUMMARY ====")
for name, n, ok, sc, p50, p95 in results:
    print(f"{name:28s} ok={ok}/{n}  p50={p50*1000:.1f}ms  p95={p95*1000:.1f}ms")
rps = 200 / results[0][4]
print(f"health approx rps(c10): {rps:.0f}")
