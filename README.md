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

## 它是什么

Grokbot-RedNote 是给 Grok Bot 用的 macOS 工具。它通过你已登录的 Chrome 会话只读搜索小红书网页，并把标题和链接带回对话。

作者：Hongtian Chan（[chenhongtian.com](https://chenhongtian.com/)，也可以叫他 Drunk）。

## 环境要求

- macOS 13 或更高
- 系统自带的 `/usr/bin/python3`，版本 3.9 或更高，无需 `pip install`
- 先用 Chrome 默认配置登录 [小红书网页](https://www.rednote.com/)

若缺少 `/usr/bin/python3`，运行 `./install.sh` 时脚本会提示安装 macOS Command Line Tools（`xcode-select --install`）。

## 克隆

```sh
git clone https://github.com/HongtianChan/Grokbot-RedNote.git
cd Grokbot-RedNote
```

## install.sh

在项目根目录运行 `./install.sh`。它会把 `launchd/com.drunk.grokbotrednote.plist` 写入 `~/Library/LaunchAgents/com.drunk.grokbotrednote.plist`（自动填入本机项目路径，无需手动改路径），并启动 `/usr/bin/python3 src/grokbot_rednote.py --service`。本地服务地址是 `http://127.0.0.1:18765`。

## start.sh

然后运行 `./start.sh`。它会执行 `open "./Grokbot-RedNote.app"`，打开项目根目录下的应用窗口。`Grokbot-RedNote.app` 不在 git 仓库中（已被 gitignore），若该文件不存在，`start.sh` 会失败。

## 确认服务在运行

```sh
curl http://127.0.0.1:18765/health
```

返回里带 `"ok": true` 即表示服务已启动。

## 如何使用

保持服务运行，让 Grok Bot 调用本地搜索接口，例如：

```sh
curl 'http://127.0.0.1:18765/search?q=关键词'
```

成功时会返回笔记的标题和链接。也可以把仓库链接交给 Grok Bot，让它帮你配置并调用。

本项目未经授权不能商用。

仓库由 Hongtian Chan 维护：[HongtianChan/Grokbot-RedNote](https://github.com/HongtianChan/Grokbot-RedNote)。
