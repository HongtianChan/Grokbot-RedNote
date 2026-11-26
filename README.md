中文 | [English](README.en.md)

<div align="center">

<img src="assets/happy.png" width="132" height="132" alt="Grokbot-RedNote">

<h1>Grokbot-RedNote</h1>

<p><strong>嘿人类，这不是给你用的。</strong></p>

<p><strong>专供 Grok Bot 使用：让它具备搜索小红书内容的能力，并把结果带回与你的对话里。</strong></p>

<table align="center">
<tr>
<td align="center" valign="top" width="512">
<img src="assets/xiaohongshu.jpg" width="240" alt="小红书：Drunk">
<br>
<sub><b>小红书</b><br>Drunk　955473847</sub>
</td>
<td align="center" valign="top" width="512">
<img src="assets/zanshang.jpg" width="240" alt="赞赏码">
<br>
<sub><b>干活不易～请我喝杯奶茶？</b></sub>
</td>
</tr>
</table>

<p>目前还在开发状态，如有bug欢迎小红书私信，想只夸夸我也不是不可以啦～ -v-</p>

<p><sub>目前仅支持macOS · 开发中 · 未经授权不能商用</sub></p>

</div>

> [!IMPORTANT]
> 这是一个**非官方**工具，开源（干活不易求打赏-v-）。它使用你自己 *已登录* 的 Chrome 会话访问小红书网页，与小红书、xAI 均无合作、授权。（如果说我是cursor和grokbot的月度股东...倒也算是（开玩笑））。

## 🧭 它是什么

Grokbot-RedNote 是给 Grok Bot 用的 macOS 工具。它通过你已登录的 Chrome 会话只读搜索小红书网页，并把标题和链接带回对话。

作者：Hongtian Chan / Drunk [chenhongtian.com](https://chenhongtian.com/)。

## 📦 环境要求

- 系统自带的 `/usr/bin/python3`，版本 3.9 或更高，无需 `pip install`。搜索服务本身只需要这个版本的 Python
- `curl`（`install.sh` 用它检查服务是否已启动）
- 先用 Chrome 默认配置登录 [小红书网页](https://www.rednote.com/)

本项目仅支持 macOS。若要打开 `start.sh` 对应的应用窗口，需要 macOS 13 或更高（该要求来自应用的 `Info.plist`）。

若缺少 `/usr/bin/python3`，运行 `./install.sh` 时脚本会提示安装 macOS Command Line Tools（`xcode-select --install`）。

## 📥 克隆

```sh
git clone https://github.com/HongtianChan/Grokbot-RedNote.git
cd Grokbot-RedNote
```

## 🛠 install.sh

在项目根目录运行 `./install.sh`。它会把 `launchd/com.drunk.grokbotrednote.plist` 写入 `~/Library/LaunchAgents/com.drunk.grokbotrednote.plist`（自动填入本机项目路径，无需手动改路径），并启动 `/usr/bin/python3 src/grokbot_rednote.py --service`。若端口 `18765` 上已经有健康的服务在运行，脚本会写入 LaunchAgent 文件但暂不加载，以免启动第二份进程。本地服务地址是 `http://127.0.0.1:18765`。

## ▶️ start-service.sh

若不想用 LaunchAgent，也可以在项目根目录运行 `./start-service.sh`。它会执行 `/usr/bin/python3 src/grokbot_rednote.py --service`，在前台启动同一个本地服务。不要在服务已经运行时再执行一次（包括刚跑完 `./install.sh` 之后），否则会因端口被占用而失败。

## ✅ 确认服务在运行

```sh
curl http://127.0.0.1:18765/health
```

返回里带 `"ok": true` 即表示服务已启动。

## 🚀 如何使用

保持服务运行，让 Grok Bot 调用本地搜索接口，例如：

```sh
curl 'http://127.0.0.1:18765/search?q=关键词'
```

成功时会返回笔记的标题和链接。也可以把仓库链接交给 Grok Bot，让它帮你配置并调用。

## 🖥 start.sh

`./start.sh` 会执行 `open "./Grokbot-RedNote.app"`，打开项目根目录下的应用窗口。这不是启动搜索服务的必要步骤。预构建的应用请到 [GitHub Releases](https://github.com/HongtianChan/Grokbot-RedNote/releases) 下载，解压后放到项目根目录。该应用是 arm64 构建，仅适用于 Apple 芯片（M 系列）Mac，无法在 Intel Mac 上运行；在其他电脑上打开时，系统可能弹出 Gatekeeper 提示。

## 🔢 每日搜索次数

从本仓库运行时，默认每天可搜索 10 次，在当地时间零点重置。本地开发或测试时，设置环境变量 `GROKBOT_REDNOTE_DEV=1`，或启动服务时加上 `--dev`，即可不限次数。

## 📄 许可证

本项目采用 [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/)。完整文本见 [LICENSE](LICENSE)。
