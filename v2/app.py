from flask import Flask, request, jsonify, send_from_directory
from paddlespeech.cli.tts import TTSExecutor
from flask_cors import CORS
from pydub import AudioSegment
import os
import re
import time
import threading

app = Flask(__name__)
CORS(app)  # 启用跨域支持
tts = TTSExecutor()

# 音频输出目录（挂载到宿主机）
output_dir = "/mnt"
files_dir = os.path.join(output_dir, "files")  # 存放合并文件的目录

# 确保 files 文件夹存在
os.makedirs(files_dir, exist_ok=True)

# 等待删除的文件队列
deletion_queue = []

# 启动删除队列处理线程
def deletion_worker():
    """定期删除等待删除队列中的文件"""
    while True:
        if deletion_queue:
            temp_file = deletion_queue.pop(0)
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    print(f"已删除文件: {temp_file}")
            except PermissionError:
                # 如果文件被占用，重新加入队列稍后再试
                print(f"无法删除文件: {temp_file}，它可能仍在被使用")
                deletion_queue.append(temp_file)
            time.sleep(1)  # 等待一段时间后再试下一个文件
        else:
            time.sleep(1)  # 如果队列为空，稍作延迟再检查

# 启动后台线程处理删除队列
threading.Thread(target=deletion_worker, daemon=True).start()

# 预加载模型，减少首次加载的延迟
def preload_model():
    print("预加载模型中...")
    tts(text="预加载", output="/dev/null")  # 调用一次 TTSExecutor，生成输出到无效路径
    print("模型预加载完成")

# 在后台线程中预加载模型
threading.Thread(target=preload_model, daemon=True).start()

@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    try:
        # 从 JSON 请求中提取文本和文件名
        data = request.get_json()
        if not data or 'name' not in data or 'text' not in data:
            return jsonify({"error": "Invalid input. 'name' and 'text' fields are required."}), 400
        
        base_name = data.get("name", "audio_segment")
        raw_text = data.get("text", "你好，欢迎使用PaddleSpeech。")
        voice = data.get("voice", "default")  # 获取音色参数，默认值为 "default"

        # 在生成新文件之前，删除 /mnt 文件夹下所有 .mp3 文件
        existing_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".mp3")]
        deletion_queue.extend(existing_files)  # 将当前的 mp3 文件加入删除队列

        # 按标点符号拆分长文本
        sentences = split_text_into_sentences(raw_text)

        # 生成音频文件并按顺序编号
        audio_files = []
        for i, sentence in enumerate(sentences):
            audio_path = os.path.join(output_dir, f"{base_name}_{i:04d}.mp3")
            generate_audio_with_voice(text=sentence, output=audio_path, voice=voice)
            audio_files.append(audio_path)
            time.sleep(0.5)  # 稍微延迟，确保文件有序生成

        # 合并音频文件
        combined_audio_path = os.path.join(files_dir, f"{base_name}.mp3")
        merge_audio_files(audio_files, combined_audio_path)

        # 将生成的分段文件加入删除队列，而不是立即删除
        deletion_queue.extend(audio_files)

        # 返回成功信息和文件路径
        return jsonify({"message": "音频生成成功", "combined_file_url": f"/files/{base_name}.mp3"}), 200

    except Exception as e:
        # 捕获所有异常并返回错误信息
        return jsonify({"error": "音频生成失败", "details": str(e)}), 500

def split_text_into_sentences(text):
    """根据标点符号将长文本拆分为短句"""
    sentences = re.split(r'(?<=[。！？])', text)  # 按句号、感叹号、问号拆分
    return [s.strip() for s in sentences if s.strip()]

def generate_audio_with_voice(text, output, voice):
    """根据指定音色生成中文音频"""
    # 选择音色（模型）
    if voice == "female":
        tts = TTSExecutor(model="fastspeech2_csmsc", voc="hifigan_csmsc", lang="zh")  # 普通话女声
    elif voice == "male":
        tts = TTSExecutor(model="fastspeech2_aishell3", voc="hifigan_aishell3", lang="zh")  # 普通话男声
    else:
        tts = TTSExecutor(model="fastspeech2_csmsc", voc="hifigan_csmsc", lang="zh")  # 默认普通话女声

    # 调用 TTSExecutor 来生成音频
    tts(text=text, output=output)

def merge_audio_files(input_files, output_file):
    """合并多个音频文件为一个"""
    combined = AudioSegment.empty()
    for file in input_files:
        audio_segment = AudioSegment.from_mp3(file)
        combined += audio_segment
    combined.export(output_file, format="mp3")

# 新增路由：提供 /mnt/files 文件夹下的文件访问
@app.route('/files/<path:filename>', methods=['GET'])
def download_file(filename):
    """提供访问 /mnt/files 文件夹下文件的接口"""
    return send_from_directory(files_dir, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)