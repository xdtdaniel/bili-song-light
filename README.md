# Bilibili Song Segment Marker (哔哩哔哩歌回路灯 / bili-song-light)

A robust, heuristic-based digital signal processing (DSP) tool to automatically identify, mark, and generate timestamps for singing segments in Bilibili livestream playbacks or local video archives.

一个基于数字信号处理（DSP）启发式算法的轻量级工具，能够自动识别 B 站录播链接或本地音视频中的唱歌片段，并一键生成精确的时间戳标记表格。

---

## Quick Navigation / 快速导航

* **[中文版说明 (Chinese Version)](#中文版说明)**
  * [核心特性](#核心特性) | [跨平台安装步骤](#跨平台环境准备) | [快速上手](#快速上手) | [调参建议](#调参建议) | [运行原理](#算法运行原理-dsp-信号处理)
* **[English Version](#english-version)**
  * [Core Features](#core-features) | [Cross-Platform Setup](#cross-platform-environment-setup) | [Quick Start](#quick-start) | [Parameter Tuning](#parameter-tuning-1) | [Under The Hood](#under-the-hood-dsp-theory)

---

## 中文版说明

### 核心特性
* **一体化流水线**：仅需单条 CLI 命令行，即可全自动处理从 B站下载、音频流提取到声学特征识别的全流程。
* **流量与带宽优化**：默认下载 B站的 `worstaudio` 格式（如 67kbps mono 单声道极低码率流），下载多小时的长录播仅需极少带宽。
* **持久化智能缓存**：全自动匹配并提取 B站 BV 视频号。若对同一个 URL 重复运行，将跳过下载，在 **2 秒内** 瞬时输出识别结果！
* **人声响度提升过滤**：引入了动态相对响度（Loudness Lift）特征，在播放高能背景音乐（BGM）期间，能够完美滤除主播纯说话/杂谈的误报。
* **稳定抗断流防卡死**：强力注入分片无限重试机制（`--fragment-retries infinite`），彻底解决 B站 CDN 频繁重置长视频连接导致音频截断损坏的问题。

---

### 跨平台环境准备

运行本项目需要系统安装 `ffmpeg` (音频转换)、`yt-dlp` (音视频下载) 和 `aria2` (多线程加速，可选)。请根据您的操作系统选择相应的安装方式：

#### macOS (使用 Homebrew)
```bash
brew install ffmpeg yt-dlp aria2
```

#### Windows
最推荐的方式是使用 Windows 自带的包管理器 **`winget`**。在 PowerShell 或 CMD 中运行：
```powershell
# 一键安装 ffmpeg, yt-dlp 和 aria2
winget install Gyan.FFmpeg
winget install yt-dlp
winget install aria2
```
*提示：安装完成后，建议重启终端以使环境变量生效。如果您不使用 winget，可以直接前往各官网下载 `.exe` 二进制文件并手动添加至系统的 PATH 环境变量中。*

#### Linux (Ubuntu / Debian / CentOS)
Linux 自带包管理器中 `yt-dlp` 的版本通常较旧，容易因 B站接口更新而报错。因此推荐从官方源直接下载最新二进制文件：
```bash
# 1. 安装 ffmpeg 和 aria2
sudo apt update && sudo apt install -y ffmpeg aria2

# 2. 从 GitHub 下载最新版 yt-dlp 二进制文件并赋予执行权限
sudo wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp
```

---

### 安装步骤

在终端或命令行中，克隆本项目，创建 Python 虚拟环境并激活，然后安装核心声学计算库：

```bash
# 1. 创建并激活虚拟环境
python3 -m venv .venv

# 激活虚拟环境 (macOS / Linux)
source .venv/bin/activate
# 激活虚拟环境 (Windows CMD)
# .venv\Scripts\activate.bat
# 激活虚拟环境 (Windows PowerShell)
# .venv\Scripts\Activate.ps1

# 2. 安装依赖
python -m pip install -r requirements.txt
```

---

### 快速上手

#### 1. 运行 B 站录播链接分析
直接提供 B 站视频/录播的播放 URL，脚本会自动将最低码率音频流下载到本地的 `work/` 目录缓存起来，并生成唱歌时间戳：
```bash
python song_marker.py \
  --url "https://www.bilibili.com/video/BV1uUVf6QEMw" \
  --threshold 0.56 \
  --min-duration 25 \
  --merge-gap 30 \
  --min-loudness-lift 0.30 \
  --downloader aria2c \
  --downloader-args "aria2c:-x 4 -s 4 -k 1M --retry-wait=2 --max-tries=0" \
  --out outputs/BV1uUVf6QEMw_segments.md
```
*(同一个 URL 二次运行会直接读取缓存，2 秒内即可秒出结果！)*

#### 2. 运行本地已有音视频分析
如果你本地已经下载好了 `.mp4`、`.m4a`、`.mp3` 或 `.wav` 文件：
```bash
python song_marker.py \
  --audio path/to/archive.mp4 \
  --threshold 0.56 \
  --min-duration 25 \
  --merge-gap 30 \
  --min-loudness-lift 0.30 \
  --out outputs/local_segments.md
```

---

### 输出格式
脚本会自动在指定的输出路径生成 Markdown 表格，列出识别出的唱歌时间段 and 详细的声学诊断参数：

```markdown
| start | end | duration | confidence | loudness_lift | voice_presence | pitch_stability |
|---:|---:|---:|---:|---:|---:|---:|
| 15:05 | 15:32 | 00:27 | 0.59 | 0.44 | 0.80 | 0.62 |
| 01:11:01 | 01:16:18 | 05:17 | 0.61 | 0.56 | 0.80 | 0.61 |
```

---

### 调参建议

你可以通过命令行传入不同的参数来精细调控歌声识别的敏感度：

| 参数 | 默认值 | 功能说明 |
| :--- | :--- | :--- |
| `--threshold` | `0.56` | 唱歌置信度分数阈值（0.0 至 1.0）。取值越高越保守，漏报越少，但漏歌率可能升高。 |
| `--min-duration` | `45.0` | 单个唱歌片段的最低持续秒数。短于此时间的候选段落会被直接过滤。 |
| `--merge-gap` | `20.0` | 两个独立唱歌片段自动合并的最大间隔秒数。少于此时间的短连唱会被合并。 |
| `--min-loudness-lift` | `0.35` | 候选歌声片段相对于局部背景底噪的平均人声响度提升阈值。 |

> [!TIP]
> **过滤主播在 BGM 期间纯说话的误报：**
> 如果主播在播放非常响亮的背景音乐（BGM）期间只是在杂谈说话，可以通过将 `--min-loudness-lift` 调高到 `0.35` 或 `0.40` 来解决。由于歌声通常伴随着持续的人声高能量抬升，提高该值能完美剪除“背景乐说话”的误报，只保留真正的唱歌片段！
>
> **捕捉超短的哼唱滑音或歌声插曲：**
> 可以将置信度 `--threshold` 降低到 `0.56` 或 `0.58`，同时将 `--min-duration` 降低到 `25` 或 `30` 秒，以便敏感地抓取短哼唱。

---

### 算法运行原理 (DSP 信号处理)
定位器基于数字信号处理（DSP）启发式算法，无需依赖厚重的深度学习模型或昂贵的 API：
1. **DASH 码率流控**：利用 `yt-dlp` 获取最低码率音频，并通过 `ffmpeg` 统一重采样输出为 16 kHz 单声道 WAV 容器以供分析。
2. **特征抽取**：按帧计算均方根能量（RMS）、过零率（ZCR）、频谱带宽（Spectral Bandwidth）以及谱平坦度（Spectral Flatness）。
3. **人声追踪**：提取人声主要频段（180 Hz 至 3.5 kHz）以获取频域人声占比，并通过 `PiPTrack` 算法追踪各帧音高，计算音高在时间滑动窗口内的稳定性。
4. **动态背景响度抬升**：以滑动大窗口的 25 分位数作为当前的动态局部背景底噪，将当前 RMS 响度与之作分贝差值计算，得到准确的动态人声抬升值。
5. **平滑滤波与时间合并**：利用滑动平均窗口对置信度分数进行平滑去噪，根据阈值截取活跃段，自动合并相邻 of 短间距段，并最后利用长度和人声抬升滤波器过滤出高纯净度的歌声片段。

---
---

## English Version

### Core Features
* **Integrated Pipeline**: Downloads, extracts, and analyzes Bilibili streams end-to-end with a single CLI command.
* **Network & Bandwidth Optimization**: Defaults to Bilibili's `worstaudio` format (e.g. 67kbps mono stream), downloading multi-hour playbacks using minimal bandwidth.
* **Persistent Smart Cache**: Automatically extracts Bilibili Video IDs (e.g., `BV...`). If ran repeatedly on the same URL, it skips downloading entirely and processes the cached file in **under 2 seconds**!
* **Acoustic Loudness Lift Filter**: Employs a relative dynamic loudness threshold to eliminate speech/talking false-positives under loud background music (BGM).
* **Anti-Disconnection**: Fortified with infinite segment retries (`--fragment-retries infinite`) to bypass aggressive Bilibili CDN rate-limiting on playbacks.

---

### Cross-Platform Environment Setup

Running this project requires system-level installations of `ffmpeg` (for audio transcoding), `yt-dlp` (for downloading), and `aria2` (optional, for download acceleration). Follow the installation guide for your OS:

#### macOS (via Homebrew)
```bash
brew install ffmpeg yt-dlp aria2
```

#### Windows
The most streamlined installation method is via **`winget`** (Windows Package Manager). Open PowerShell or Command Prompt and run:
```powershell
winget install Gyan.FFmpeg
winget install yt-dlp
winget install aria2
```
*Note: We highly recommend restarting your terminal shell after installation to refresh PATH variables. If you don't use winget, please download the official .exe binaries and add them to your system's PATH manual configuration.*

#### Linux (Ubuntu / Debian / CentOS)
Standard package managers often ship outdated versions of `yt-dlp` that fail due to Bilibili API updates. We recommend downloading the latest official binary directly:
```bash
# 1. Install ffmpeg and aria2
sudo apt update && sudo apt install -y ffmpeg aria2

# 2. Download the latest official yt-dlp build and make it executable
sudo wget https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp
```

---

### Installation

Clone the repository, initialize and activate a Python virtual environment, and install the required numerical computing dependencies:

```bash
# 1. Create and activate venv
python3 -m venv .venv

# Activate (macOS / Linux)
source .venv/bin/activate
# Activate (Windows CMD)
# .venv\Scripts\activate.bat
# Activate (Windows PowerShell)
# .venv\Scripts\Activate.ps1

# 2. Install Python packages
python -m pip install -r requirements.txt
```

---

### Quick Start

#### 1. Run via Bilibili Playback URL
Provide the Bilibili URL directly. The tool will download the lowest bandwidth stream format to the local `work/` directory, cache it, and execute segment identification:
```bash
python song_marker.py \
  --url "https://www.bilibili.com/video/BV1uUVf6QEMw" \
  --threshold 0.56 \
  --min-duration 25 \
  --merge-gap 30 \
  --min-loudness-lift 0.30 \
  --downloader aria2c \
  --downloader-args "aria2c:-x 4 -s 4 -k 1M --retry-wait=2 --max-tries=0" \
  --out outputs/BV1uUVf6QEMw_segments.md
```
*(On subsequent runs of the same URL, the download is skipped entirely and runs instantly!).*

#### 2. Run via Local Video/Audio File
If you already have a pre-downloaded `.mp4`, `.m4a`, `.mp3` or `.wav` file on your disk:
```bash
python song_marker.py \
  --audio path/to/archive.mp4 \
  --threshold 0.56 \
  --min-duration 25 \
  --merge-gap 30 \
  --min-loudness-lift 0.30 \
  --out outputs/local_segments.md
```

---

### Output Format
The script generates a Markdown table listing identified singing segments, together with diagnostic acoustic metrics:

```markdown
| start | end | duration | confidence | loudness_lift | voice_presence | pitch_stability |
|---:|---:|---:|---:|---:|---:|---:|
| 15:05 | 15:32 | 00:27 | 0.59 | 0.44 | 0.80 | 0.62 |
| 01:11:01 | 01:16:18 | 05:17 | 0.61 | 0.56 | 0.80 | 0.61 |
```

---

### Parameter Tuning

You can fine-tune the detection using the following CLI arguments:

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `--threshold` | `0.56` | Confidence threshold (0.0 to 1.0) for singing. Higher values are more conservative. |
| `--min-duration` | `45.0` | Minimum duration (in seconds) of a valid singing segment. Shorter ones will be filtered. |
| `--merge-gap` | `20.0` | Maximum gap (in seconds) between two segments to merge them. |
| `--min-loudness-lift` | `0.35` | The average relative loudness lift of vocal frequencies over background. |

> [!TIP]
> **To filter out speech false positives during BGM:**
> If the streamer is just talking or hosting a chat session while playing loud BGM, increase `--min-loudness-lift` to `0.35` or `0.40`. Since singing requires continuous high vocal energy, this will eliminate background chatter false-positives while keeping true songs intact!
>
> **To capture short song previews or slips:**
> Lower `--threshold` to `0.56` or `0.58` and reduce `--min-duration` to `25` or `30` seconds.

---

### Under The Hood (DSP Theory)
The algorithm works sequentially through Digital Signal Processing (DSP) heuristics without relying on heavy deep-learning models:
1. **DASH Audio Streaming**: Automatically targets the lowest DASH audio stream (`worstaudio`) using `yt-dlp` and resamples to a uniform mono WAV container via `ffmpeg`.
2. **Feature Extraction**: Evaluates frame-level Root Mean Square (RMS) energy, Zero Crossing Rate (ZCR), Spectral Bandwidth, and Spectral Flatness.
3. **Vocal Tracking**: Extracts vocal frequencies (180 Hz to 3.5 kHz) using STFT magnitude to evaluate vocal presence, and uses Pitch Tracking (via PiPTrack) to compute pitch stability over sliding windows.
4. **Local Loudness Lift Calculation**: Computes dynamic relative loudness by comparing active frames to the local 25th percentile background floor, converting to normalized decibel lift values.
5. **Smoothing & Temporal Merging**: Applies a moving-average window to smooth frames, segments active timestamps based on thresholding, merges short gaps, and discards segments failing duration/loudness filters.

---

## License
MIT License. Feel free to use, modify, and publish.
欢迎自由提 Issue 或 PR！
