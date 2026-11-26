[中文](README.md) | English

<div align="center">

<img src="assets/happy.png" width="132" height="132" alt="Grokbot-RedNote">

<h1>Grokbot-RedNote</h1>

<p><strong>Hey human, this is not for you.</strong></p>

<p><strong>Made for Grok Bot: it gives Grok Bot the ability to search Xiaohongshu and bring the results back into your conversation.</strong></p>

<table align="center">
<tr>
<td align="center" valign="top" width="512">
<img src="assets/xiaohongshu.jpg" width="240" alt="Xiaohongshu: Drunk">
<br>
<sub><b>Xiaohongshu</b><br>Drunk　955473847</sub>
</td>
<td align="center" valign="top" width="512">
<img src="assets/zanshang.jpg" width="240" alt="Tip QR code">
<br>
<sub><b>This takes work — treat me to a milk tea?</b></sub>
</td>
</tr>
</table>

<p>Still in development. If you find a bug, feel free to message me on Xiaohongshu. Compliments are welcome too~ -v-</p>

<p><sub>macOS only · in development · not for commercial use without permission</sub></p>

</div>

> [!IMPORTANT]
> This is an **unofficial** tool, and it is open source (this takes work, tips welcome -v-). It uses your own *already signed-in* Chrome session to visit the Xiaohongshu website, and has no partnership or authorization with Xiaohongshu or xAI. (If I said I were a monthly shareholder of Cursor and Grok Bot... that was a joke.)

## 🧭 What it is

Grokbot-RedNote is a macOS tool for Grok Bot. It searches Xiaohongshu pages read-only through your signed-in Chrome session, and brings titles and links back into the conversation.

Author: Hongtian Chan ([chenhongtian.com](https://chenhongtian.com/), also called Drunk).

## 📦 Prerequisites

- macOS 13 or later
- System `/usr/bin/python3`, version 3.9 or later; no `pip install` needed
- First sign in to the [Xiaohongshu website](https://www.rednote.com/) with Chrome's default profile

If `/usr/bin/python3` is missing, `./install.sh` will tell you to install the macOS Command Line Tools (`xcode-select --install`).

## 📥 Clone

```sh
git clone https://github.com/HongtianChan/Grokbot-RedNote.git
cd Grokbot-RedNote
```

## 🛠 install.sh

Run `./install.sh` from the project root. It writes `launchd/com.drunk.grokbotrednote.plist` to `~/Library/LaunchAgents/com.drunk.grokbotrednote.plist` (filling in this machine's project path, so you do not have to edit paths by hand) and starts `/usr/bin/python3 src/grokbot_rednote.py --service`. The local service address is `http://127.0.0.1:18765`.

## 🖥 start.sh

Then run `./start.sh`. It runs `open "./Grokbot-RedNote.app"` and opens the app window from the project root. `Grokbot-RedNote.app` is not in the git repository (it is gitignored); if the file is missing, `start.sh` will fail.

## ✅ Check that the service is running

```sh
curl http://127.0.0.1:18765/health
```

A response that includes `"ok": true` means the service is up.

## 🚀 How to use it

Keep the service running, and let Grok Bot call the local search API, for example:

```sh
curl 'http://127.0.0.1:18765/search?q=keyword'
```

On success, it returns note titles and links. You can also give Grok Bot the repository link and ask it to set this up and call the API for you.

This project may not be used commercially without permission.

This repository is maintained by 陈鸿天 (Hongtian Chan).
