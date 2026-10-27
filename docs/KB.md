# APK 逆向 → 2API 交付知识库

> 跨项目方法论沉淀。案例：NoTrackAI、OpenChat、Imagenai、Imagerator、AI视频成片、Nano Banana、phota3a、**Photoroom**。
> 配套：skill `~/.claude/skills/apk-to-2api/SKILL.md`（9 步 SOP + 阶段二 new-api 移植）、memoir `apk-2api-sop`（知识图谱）、ICM topic `context-new-api-Max`。

---

## 一、鉴权模式全谱（按破解难度升序）

| 模式 | 识别特征 | 破解要点 | 案例 |
|---|---|---|---|
| 无鉴权 | 400 missing_image 而非 401 | 直接调 | Photoroom segmentation |
| 静态 key | 硬编码 header（X-App-Key 等） | grep dex 字符串 | NoTrackAI |
| 动态签名 | X-App-Sig = f(签名证书) | SHA1/SHA256 离线复现 | NoTrackAI（`g50.java`） |
| **Firebase 匿名** | dex 有 FirebaseAuth + AIza key | 见下节 | **Photoroom** |
| magic code / 短信 | request-code 端点 + 验证码 | 需真实邮箱/手机；device_id 伪造可绕时优先 | Imagenai、AI视频成片 |
| 服务器 RSA 下发凭据 | findConfig 类接口 + 内嵌私钥 | raw socket 调接口解密 | Nano Banana |
| Play Integrity / 设备指纹 | 设备注册接口 + 硬件证明 | 模拟器农场或放弃 | nano-banana 教训 |

### Firebase 匿名链路（Photoroom 实战，通用性强）

```
① 注册（免验证）
POST https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=<AIza...>
  X-Android-Package: <app 包名>          ← 缺一即 403 API_KEY_ANDROID_APP_BLOCKED
  X-Android-Cert: <官方签名 SHA1>        ← 破解壳 bin.Apk.daddy 内嵌 PEM → sha1
  {"returnSecureToken": true}
→ {idToken(1h), refreshToken(永久), localId}

② 刷新（离线可持续）
POST https://securetoken.googleapis.com/v1/token?key=...
  grant_type=refresh_token&refresh_token=<rt>

③ 上游调用（⚠️ 关键差异）
Authorization: <裸 idToken>     ← 不带 Bearer！带 Bearer 反而 403 "Firebase: Invalid token"
```

SHA1 提取三种来源：① SignatureKillerEx 壳内嵌 PEM（破解版特有，最方便）② 正版 APK `keytool -printcert` ③ app 内硬编码字符串。

### 免费号池模式（Imagerator 首创，注册无验证时）

`device_id=uuid4().hex` 伪造注册 → `[id, credits, ts]` 池 + `_pool_lock` 并发安全 → 耗尽先同步上游真实余额 → 仍不足注册新号（重试 3）→ `device_pool.json` 持久化。Go 移植版见 `device-pool-golang` memoir 概念。

---

## 二、协议还原方法论

### 2.1 端点发现
1. 全 dex grep `https?://` → 排噪（google/play/ads/crashlytics）→ 业务域名清单
2. dex 内 grep 版本化路径 `"v[0-9]/..."` → 端点+所在接口类
3. Retrofit 接口类直接读：注解+参数即完整请求定义

### 2.2 R8 混淆注解还原（行为验证法）
jadx 会把 `retrofit2.http.*` 重命名成 b7c/i3l/h3l 等短名，dex 里 retrofit 字符串被 strip。**别猜，实测**：

| 混淆名 | 真身 | 判据 |
|---|---|---|
| `@b7c` | GET | gfonts json 下载类端点 GET 实测 200 |
| `@i3l` | POST | 带 @ur3 body；405 探测 |
| `@tgj` | Multipart | 多 Part 参数 |
| `@eel` | Part | MultipartBody.Part 参数 |
| `@ptn` | Query | 原始类型参数 |
| `@s7d` | Header | String 参数 |
| `@ur3` | Body | POJO 参数 |

405 响应自带 allowed methods（NestJS 最详细），一发就能确认。

### 2.3 host 归属（多服务器 app 必查）
同一 app 的端点分布多台上游，**打错 host = 404/502/500 假象**。查 Retrofit 装配（搜 `RetrofitPhotoroom*` / `n1p.b("https://...")` / nz5 型 switch-case 工厂）。
> Photoroom 教训：inpaint 502 卡了半小时，真因是 host 该是 segmentation-inference 而非 serverless。

### 2.4 multipart 字段名（逐台探测）
各上游字段名可能不一致（Photoroom: `sourceImage` / `imageFile` / `maskFile` 三种）。探测信号：
- 400 `missing_image`（Flask）= 字段名错
- 403 鉴权错 = **字段名对了**（走到鉴权层了）
- 422 `field required: body.imageFile`（FastAPI）= 直接告诉你字段名

### 2.5 b64 图片上传
先试裸 base64，再试 `data:image/...;base64,` 前缀。Photoroom inpaint：裸 b64 ✅、data-uri 500。反过来也有 app。

---

## 三、坑位总表（按事故率排序）

| 坑 | 症状 | 解法 |
|---|---|---|
| **Authorization 带 Bearer**（Firebase Admin 后端） | 403 Invalid token | 裸 token |
| **Firebase key 双头缺失** | 403 API_KEY_ANDROID_APP_BLOCKED | X-Android-Package + X-Android-Cert |
| **multipart 字段名错** | 400 missing_image | 逐个候选名探测（sourceImage/imageFile/image/file） |
| **host 打错** | 404/502 假象 | 查 Retrofit 装配 |
| **405 误判为 POST 端点** | 全部 405 | GET+query 实测（magic code 类常是 GET） |
| **mask 面积过大** | 上游 500 无 detail | mask <50% 面积 |
| **上游偶发 IncompleteRead** | 偶发 500/502 | 重试；画布尺寸用目标值（勿变形） |
| **uncrop/画布类** | 随便传图报 decode 失败 | 需按目标尺寸构造画布+mask（读 app 端构造类） |
| **passthrough 跳过 Convert**（new-api 阶段二） | 上游收缺省字段 422 | DoRequest 里统一判空补默认 |
| **改代码没生效** | 旧进程占端口 | `taskkill //F //IM python.exe` 全杀再启 |
| **凭据两套并存** | 一套能用一套死 | 分别实测权限矩阵 |
| **模拟器干扰** | app 行为异常 | `pm disable-user` 禁用分析残留 app |

---

## 四、压测规范

- **只压自己的 demo server，绝不压上游**（红线）
- 场景组合：轻端点（health ×200 c10 + ×60 c60）→ 核心能力（×4~12 c2~c4）→ 错误路径（no-auth 401 / unknown 404 / no-image 400 / 边界值 clamp）
- 指标：ok/n、p50、p95、sample_codes
- 结论模板：网关自身开销（轻端点 p50）vs 上游推理耗时（核心端点 p50），分开报

## 五、交付清单（每个 2API 项目）

```
D:/{app}-2api-app/
├── demo_server.py      # ThreadingHTTPServer, 网关+网页demo, token自动注册/刷新/持久化
├── stress_test.py      # 9+ 场景
├── README.md           # 端点清单/鉴权链路/压测表/坑位/关键反编译文件
├── PROTOCOL.md         # 协议笔记（UTF-8!）
├── anon_token.json     # token 持久化(gitignore)
└── .gitignore          # jadx-out/ apk-unzip/ *.apk demo.log
```

GitHub：`lza6/{AppName}-2API-APP` + topics `reverse-engineering,android,apk-analysis,security-research,2api`
记忆：ICM `context-new-api-Max`（进度）+ memoir `apk-2api-sop`（方法图谱）+ 本文件更新

## 六、new-api 移植速查（阶段二）

- 渠道 type 从 68 起找空位（已占 62-67）；6 文件注册链见 SKILL.md
- 适配器模板选型：单轮 JSON→kilwa / SSE→notrack / 异步任务→imagerator / **图像编辑类→Photoroom 模式**（`relay/channel/photoroom/` 待建：ConvertImageRequest 分流 mask/upscale/erase/fill/inpaint/uncrop）
- 验证门禁：`go build ./...` + `go vet` + `go test` + `bun run build` + version-consistency
- 生产部署：git clone 秒建（勿 tar 610M）、VERSION 文件定镜像版本、deploy-zero-downtime.sh 蓝绿、显式 INSERT abilities
- E2E：`tokens 表 id=48` 取 key，Caddyfile 查当前端口 3000/3001

---
*更新: 2026-10-27 · Photoroom 案例并入*
