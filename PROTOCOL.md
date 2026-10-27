# Photoroom v2026.37.01 协议还原

## 上游域名
- api.photoroom.com — 主API(NestJS, entitlement/user)
- segmentation-inference.photoroom.com — v1/mask 抠图(Flask)
- serverless-api.photoroom.com — v3/upscale, v1/inpaint(FastAPI)
- diffusion-backend.photoroom.com — v1/erase, v1/fill(Flask)

## 鉴权
Firebase 匿名注册: identitytoolkit accounts:signUp + X-Android-Package com.photoroom.app + X-Android-Cert 0424A4898A4B33940D8BF16E44251B876E97F8D0 (官方SHA1, 从破解壳 daddy.java PEM 提取)
上游 header: Authorization: <raw idToken> — 无 Bearer! (带 Bearer 403)
刷新: securetoken v1/token grant_type=refresh_token

## 已验证端点
1. segmentation /v1/mask multipart sourceImage+user_id+resize_mask+model_type+experiment_flag -> {b64_mask} (1536x1536 L)
2. serverless /v3/upscale multipart imageFile+outputFormat -> png 2x
3. diffusion /v1/erase multipart imageFile+maskFile -> image
4. diffusion /v1/fill multipart imageFile+maskFile+prompt+seed -> jpeg
5. api /v1/user/entitlement (GET) -> entitlements 空
6. api /v1/user/request-magic-code?email=&language= GET 免鉴权 (真人账号备用路径)

## Firebase
project background-7ef44 / 1:456289768976:android:30c90b24b80bc2d1bfdc95 / key 仅 Android client 校验
