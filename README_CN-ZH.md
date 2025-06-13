# StarTimes 视频下载工具

基于 Python 开发的StarTimes APP 专用视频下载程序。本软件正在持续完善中，欢迎提交改进建议！

---
## 文档语言
[English](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/README.md) | [中文](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/README_CN-ZH.md)

---
## 安装依赖

     "pip install -r requirements.txt"
---

## 使用指南
输入通过抓包获取的 **M3U8链接** 和 **Cookie值** 即可下载。

---

## 如何获取 M3U8 链接与 Cookie？ (ProxyPin 示例)

### 环境配置
1. **安装 HTTPS 证书**  
   Root 用户：请使用 Root 权限安装根证书
   *非 Root 用户：按标准流程安装证书*

2. **配置白名单**
   - 进入 `Proxy Filter` → `App Whitelist`
   - 启用 `Whitelist Mode`（开关设为 ON）
   - 点击 `+` 添加StarTimes APP  
   ![白名单配置示意图](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/IMG/IMG1-P4.png)

### 抓包流程
3. **启动抓包**
   - 返回抓包主界面
   - 搜索以下关键字：
     ```bash
     "m3u8"
     "gcp-video.gslb.startimestv.com"
     "vod_g"
     ```

4. **关键数据提取**
   | 页面位置        | 目标数据               | 示意图示例           |
   |----------------|-----------------------|---------------------|
   | `General` 标签页 | M3U8 链接            | ![General页](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/IMG/IMG2-P1.png) |
   | `Request` 请求头 | Cookie 值           | ![Request头](https://github.com/Rckmuyue/StarTimes-Video-Download-Tool/blob/main/IMG/IMG2-P2.png) |

---

## 常见问题
若下载失败，请修改源码中的请求参数：  
`headers = {` (第116-129行)

---

## 免责声明
>  **重要提示**  
> 本工具**仅限学习用途**。使用者需自行承担因违反当地法律或星时光用户协议所产生的一切责任，开发者概不负责。