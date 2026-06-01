import gradio as gr
import re
import tempfile
import sys
from pathlib import Path
import song_marker

def analyze_bilibili(url, threshold, min_duration, merge_gap, min_loudness_lift):
    if not url:
        return "### ⚠️ Please enter a Bilibili URL or upload a file first."
    
    # Simple URL format checker
    match = re.search(r'(BV[a-zA-Z0-9]+|av[0-9]+)', url)
    video_id = match.group(1) if match else "downloaded_audio"
    
    try:
        # Create a temp directory for the download and WAV conversion
        with tempfile.TemporaryDirectory(prefix="bili-song-light-") as tmp:
            tmp_path = Path(tmp)
            work_dir = tmp_path / "work"
            work_dir.mkdir(parents=True, exist_ok=True)
            
            # Step 1: Download
            gr.Info(f"Step 1: Downloading stream {video_id} using minimum bandwidth...")
            source = song_marker.download_audio(
                url=url,
                output_dir=work_dir,
                video_id=video_id,
                format_selector="worstaudio",
                retries=20,
                http_chunk_size=None,
                downloader="aria2c",
                downloader_args="aria2c:-x 4 -s 4 -k 1M --retry-wait=2 --max-tries=0",
            )
            
            # Step 2: Convert to WAV
            gr.Info("Step 2: Transcoding stream to 16kHz mono WAV...")
            wav_path = tmp_path / "audio.wav"
            song_marker.convert_to_wav(source, wav_path)
            
            # Step 3: Audio DSP Feature Extraction
            gr.Info("Step 3: Analyzing acoustic features (RMS, Pitch stability, Vocal presence)...")
            segments = song_marker.detect_segments(
                wav_path=wav_path,
                threshold=threshold,
                min_duration=min_duration,
                merge_gap=merge_gap,
                min_loudness_lift=min_loudness_lift,
            )
            
            # Step 4: Format Markdown Output
            gr.Info("Step 4: Writing Markdown segment list...")
            lines = [
                f"### 🎵 Analysis complete for Bilibili Video ID: `{video_id}`",
                f"Found **{len(segments)}** singing segment(s) with your settings.",
                "",
                "| Start | End | Duration | Confidence | Loudness Lift | Voice Presence | Pitch Stability |",
                "|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for seg in segments:
                lines.append(
                    f"| **{song_marker.fmt_time(seg.start)}** | **{song_marker.fmt_time(seg.end)}** | {song_marker.fmt_time(seg.duration)} | {seg.confidence:.2f} | {seg.loudness_lift:.2f} | {seg.voice_presence:.2f} | {seg.pitch_stability:.2f} |"
                )
            if not segments:
                lines.append("| No singing segments matched | - | - | - | - | - | - |")
            
            return "\n".join(lines)
            
    except Exception as e:
        return f"### ❌ Error occurred during analysis:\n```text\n{str(e)}\n```"

# Premium Gradio interface design
with gr.Blocks(theme=gr.themes.Soft(primary_hue="pink", secondary_hue="rose")) as demo:
    gr.Markdown(
        """
        # 哔哩哔哩歌回路灯 (bili-song-light) 💡
        ### Bilibili singing timestamps marker powered by audio digital signal processing (DSP)
        
        Paste a Bilibili livestream playback or video URL below, tune the acoustic sliders, and click **Analyze** to automatically extract singing segment timestamps in real-time.
        
        输入一个 B 站录播链接或视频链接，微调声学特征滑块，点击 **Analyze** 即可通过底层数字信号处理算法全自动提取唱歌时间戳，完美剔除说话和杂谈！
        """
    )
    
    with gr.Row():
        with gr.Column(scale=1):
            url_input = gr.Textbox(
                label="Bilibili URL (B站链接)", 
                placeholder="https://www.bilibili.com/video/BV...",
                value=""
            )
            
            with gr.Accordion("Advanced Parameter Tuning / 声学特征精细调参", open=True):
                threshold_slider = gr.Slider(
                    minimum=0.3, maximum=0.9, step=0.01, value=0.56,
                    label="Confidence Threshold (置信度阈值)",
                    info="Higher values filter speech better but might miss breathy singing (越高越保守，过滤说话效果好)"
                )
                duration_slider = gr.Slider(
                    minimum=5, maximum=180, step=1, value=25,
                    label="Minimum Duration in seconds (最小唱歌时长)",
                    info="Shorter snippets will be ignored (秒，过滤短插曲或哼唱)"
                )
                gap_slider = gr.Slider(
                    minimum=5, maximum=120, step=1, value=30,
                    label="Merge Gap in seconds (合并最大间隔)",
                    info="Connect two singing parts with small gaps (秒，自动合并连唱的时间间距)"
                )
                loudness_slider = gr.Slider(
                    minimum=0.0, maximum=1.5, step=0.05, value=0.30,
                    label="Minimum Loudness Lift (最小人声响度提升)",
                    info="Filter out talking false-positives during high BGM (提升分贝系数，完美过滤配乐杂谈)"
                )
            
            submit_btn = gr.Button("Analyze (点此分析) 🚀", variant="primary")
            
        with gr.Column(scale=1):
            markdown_output = gr.Markdown(
                label="Segments Output",
                value="### 📋 Timestamps Table will appear here\n*Enter a URL and click Analyze to start!*"
            )
            
    gr.Examples(
        examples=[
            ["https://www.bilibili.com/video/BV1uUVf6QEMw", 0.56, 25, 30, 0.30],
        ],
        inputs=[url_input, threshold_slider, duration_slider, gap_slider, loudness_slider],
        label="Quick Test Examples (快捷测试示例)",
    )
    
    gr.Markdown(
        """
        ---
        💡 *bili-song-light is a fully open-source, client-less, VM-free audio heuristic tool.*
        📦 **GitHub Repository:** [xdtdaniel/bili-song-light](https://github.com/xdtdaniel/bili-song-light)
        """
    )

if __name__ == "__main__":
    demo.launch()
