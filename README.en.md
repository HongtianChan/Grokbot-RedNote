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

- System `/usr/bin/python3`, version 3.9 or later; no `pip install` needed. The search service itself only requires this version of Python
- `curl` (`install.sh` uses it to check whether the service is up)
- First sign in to the [Xiaohongshu website](https://www.rednote.com/) with Chrome's default profile

This project supports macOS only. Opening the app window with `start.sh` requires macOS 13 or later (that requirement comes from the app's `Info.plist`).

If `/usr/bin/python3` is missing, `./install.sh` will tell you to install the macOS Command Line Tools (`xcode-select --install`).

## 📥 Clone

```sh
git clone https://github.com/HongtianChan/Grokbot-RedNote.git
cd Grokbot-RedNote
```

## 🛠 install.sh

Run `./install.sh` from the project root. It writes `launchd/com.drunk.grokbotrednote.plist` to `~/Library/LaunchAgents/com.drunk.grokbotrednote.plist` (filling in this machine's project path, so you do not have to edit paths by hand) and starts `/usr/bin/python3 src/grokbot_rednote.py --service`. If a healthy service is already running on port `18765`, the script writes the LaunchAgent file but does not load it yet, so it will not start a second copy. The local service address is `http://127.0.0.1:18765`.

## ▶️ start-service.sh

If you do not want a LaunchAgent, you can run `./start-service.sh` from the project root instead. It runs `/usr/bin/python3 src/grokbot_rednote.py --service` and starts the same local service in the foreground. Do not run it again while the service is already running (including right after `./install.sh`), or it will fail because the port is already in use.

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

## 🖥 start.sh

`./start.sh` runs `open "./Grokbot-RedNote.app"` and opens the app window from the project root. This is not required to start the search service. Get the prebuilt app from [GitHub Releases](https://github.com/HongtianChan/Grokbot-RedNote/releases), unzip it, and place it in the project root. The app is an arm64 build for Apple Silicon (M-chip) Macs only. It will not run on Intel Macs, and other machines may see a Gatekeeper prompt.

## 📄 License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/). See [LICENSE](LICENSE) for the full text.
