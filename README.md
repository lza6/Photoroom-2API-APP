# Photoroom 2API (v2026.37.01)

APK 逆向 → OpenAI 兼容 2API 网关。目标 APK：`Photoroom v2026.37.01`（apkdaddy/ApkSignatureKillerEx 破解版，122MB）。

## 端点清单（demo_server.py, 端口 8908）

| 路径 | 说明 | 上游 |
|---|---|---|
| `GET /health` | 状态 + 当前匿名 uid | identitytoolkit |
| `POST /api/mask` | AI 抠图（multipart: image, model_type=person/object/graphics/standard） | segmentation-inference `/v1/mask` |
| `POST /api/upscale` | 2x 超分（multipart: image） | serverless-api `/v3/upscale` |
| `POST /api/erase` | AI 擦除（image + mask 白=擦除） | diffusion-backend `/v1/erase` |
| `POST /api/fill` | AI 生成填充（image + mask + prompt） | diffusion-backend `/v1/fill` |
| `POST /api/inpaint` | AI 局部重绘（image + mask 白=重绘区；mask 面积需 <50%） | segmentation-inference `/v1/inpaint` |
| `POST /api/uncrop` | AI 外扩（image + target_w/target_h，默认 1.5x，≤2048） | serverless-api `/v2/uncrop`（服务端自动构画布+mask） |
| `POST /v1/images/edits` | OpenAI 兼容抠图 → 透明底 PNG（b64_json） | 组合 mask+alpha 合成 |

鉴权：`Authorization: Bearer sk-photoroom-demo`（环境变量 `DEMO_KEY` 可改）
网页 demo：`http://127.0.0.1:8908/`

## 鉴权链路（核心还原）

```
Firebase 匿名注册:
POST https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=AIzaSyAJGrgbFGB_-h8V2oJLr4b-_ipetqM0duU
  X-Android-Package: com.photoroom.app
  X-Android-Cert: 0424A4898A4B33940D8BF16E44251B876E97F8D0   ← 官方签名 SHA1
  {"returnSecureToken": true}  →  idToken(1h) + refreshToken(永久)
刷新: POST securetoken.googleapis.com/v1/token?key=...  grant_type=refresh_token

上游调用 header:  Authorization: <raw idToken>   ⚠️ 不带 Bearer（带 Bearer 反而 403）
```

证书指纹提取自破解壳 `bin.Apk.daddy`（ApkSignatureKillerEx 内嵌官方 PEM）。

## 第一轮压测（本地 demo，2026-10-27）

| 场景 | n | ok | p50 | p95 |
|---|---|---|---|---|
| health ×200 c10 | 200 | 200 | 1.9ms | 19ms |
| health ×60 c60 | 60 | 60 | 3.5ms | 516ms(首次冷启动) |
| 抠图 ×12 c4 | 12 | 12 | 1813ms | 2331ms |
| OpenAI edits ×6 c2 | 6 | 6 | 1223ms | 1658ms |
| upscale ×4 c2 | 4 | 4 | 2793ms | 2987ms |
| erase ×4 c2 | 4 | 4 | 1186ms | 1263ms |
| fill ×4 c2 | 4 | 4 | 2217ms | 2622ms |

错误路径：no-auth 401 / unknown 404 / no-image 400。耗时瓶颈全在上游推理（1.2-3s），网关自身开销 <2ms。

## 第二轮：uncrop/inpaint 深挖（2026-10-27）

**uncrop 协议还原**（`defpackage/a1l.java` + `qqt.java`）：
- `imageFile` = 目标尺寸画布（长边 ≤1120 缩放），原图居中绘于画布
- `maskFile` = 原图 alpha 轮廓（白=已有像素，黑=待生成），PNG，≤2048
- 响应 `image/jpeg`（尺寸=画布），响应头 `PR-UNCROP-PROMPT` 回传实际 prompt
- 实测 4 种目标尺寸全通过（512²、384×512、256²、800×600）

**inpaint 协议还原**（`defpackage/a4f.java` + `r3f.java` + `d4f.java` + `b4f.java`）：
- Host 是 **segmentation-inference**（不是 serverless！`RetrofitPhotoroomSegmentation` 装配）
- JSON body：`{b64_img, b64_mask, strokes: [{size: float, points: [[y,x],...]}], experiment_flag}` — **b64 不带 data: 前缀**
- 响应 JSON：`{model_version: "DefaultInpaintingV1", result: "<b64 jpeg>", experiment_success: true}`
- ⚠️ mask 面积 >50% 时上游 500（内部限制）

## 第二轮压测（9 场景）

| 场景 | n | ok | p50 | p95 |
|---|---|---|---|---|
| health ×200 c10 | 200 | 200 | 2.9ms | 25ms |
| 抠图 ×12 c4 | 12 | 12 | 1845ms | 3832ms |
| OpenAI edits ×6 c2 | 6 | 6 | 2796ms | 3204ms |
| upscale ×4 c2 | 4 | 4 | 7068ms | 8066ms |
| erase ×4 c2 | 4 | 4 | 2037ms | 2562ms |
| fill ×4 c2 | 4 | 4 | 4078ms | 4909ms |
| inpaint ×4 c2 | 4 | 4 | 4016ms | 4569ms |
| uncrop ×4 c2 | 4 | 3(+1 上游偶发 500) | 4782ms | — |

## 坑位记录

1. **Authorization 无 Bearer** — `Bearer` 前缀导致 403 `Firebase: Invalid token`（Firebase Admin lookup 用 raw token）
2. **multipart 字段名**：segmentation 用 `sourceImage`，serverless/diffusion 用 `imageFile`/`maskFile`——三台服务器字段名不一致
3. **Firebase key 仅允许 Android client** — 必须带 `X-Android-Package` + `X-Android-Cert`（SHA1）头，缺失/错误 → `API_KEY_ANDROID_APP_BLOCKED`
4. `@b7c` 注解 = GET（`request-magic-code` 是 GET+query，不是 POST）
5. `v1/inpaint` 上游 502 → **已解决**：host 是 segmentation-inference 非 serverless，b64 不带 `data:` 前缀
6. `v2/uncrop` 需要按目标尺寸构造的画布+mask（app 端 a1l 逻辑），非任意图直传
7. inpaint mask 面积 >50% 上游 500；uncrop 上游偶发 IncompleteRead（重试可解）
8. uncrop 上游对画布与 mask 尺寸一致性敏感 → demo server 直接用目标尺寸作画布最稳

## 关键反编译源文件

- `bin/Apk/daddy.java` — 破解壳（含官方签名 PEM）
- `defpackage/wcu.java` — magic code 登录接口（GET v1/user/request-magic-code）
- `defpackage/mgo.java` / `gvp.java` — v1/mask 调用（sourceImage 字段名来源）
- `defpackage/k3u.java` — v3/v2 upscale 接口
- `defpackage/wr0.java` — erase/fill 接口
- `defpackage/nz5.java` — OkHttpClient/Retrofit 装配（各域名的 base URL）
- `com/photoroom/engine/ModelType.java` — model_type 枚举

## 文件

- `demo_server.py` — 网关（匿名号自动注册/刷新/持久化 anon_token.json）
- `stress_test.py` — 压测脚本
- `PROTOCOL.md` — 协议还原笔记（GBK 乱码，重存 UTF-8 见下）
- `jadx-out/` — 反编译源码（不入库）
## 关键反编译源文件（第二轮补充）

- `defpackage/a1l.java` + `qqt.java` — uncrop 画布/mask 构造算法
- `defpackage/a4f.java` + `y3f.java` — inpaint 业务链
- `defpackage/r3f.java` + `b4f.java` + `d4f.java` — InpaintRequest/strokes 序列化
