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

output_dir = "/mnt"
files_dir = os.path.join(output_dir, "files")  # 存放合并文件的目录
os.makedirs(files_dir, exist_ok=True)  # 确保文件夹存在

deletion_queue = []  # 等待删除的文件队列
stop_flag = False  # 中断标志
current_thread = None  # 当前运行的线程

class TTSManager:
    """管理不同的 TTS 模型实例"""
    def __init__(self):
        self.models = {}

    def _load_model(self, model_type):
        """延迟加载模型"""
        print(f"正在加载模型: {model_type}...")
        if model_type == 'default':  # 默认女声
            model = TTSExecutor()
        elif model_type == 'male':  # 男声模型
            model = TTSExecutor()
            model(
                text="测试加载",
                am='fastspeech2_male',
                lang='zh',
                am_config='/mnt/models/fastspeech2_male_zh/default.yaml',
                am_ckpt='/mnt/models/fastspeech2_male_zh/snapshot_iter_76000.pdz',
                am_stat='/mnt/models/fastspeech2_male_zh/speech_stats.npy',
                phones_dict='/mnt/models/fastspeech2_male_zh/phone_id_map.txt',
                voc='hifigan_aishell3',
                voc_config='/mnt/models/hifigan_aishell3/default.yaml',
                voc_ckpt='/mnt/models/hifigan_aishell3/snapshot_iter_2500000.pdz',
                voc_stat='/mnt/models/hifigan_aishell3/feats_stats.npy',
            )
        elif model_type == 'aishell3':  # AISHELL3 模型
            model = TTSExecutor()
            model(
                text="测试加载",
                spk_id=0,  # 默认 speaker id
                am='fastspeech2_aishell3',
                lang='zh',
                am_config='/mnt/models/fastspeech2_aishell3/default.yaml',
                am_ckpt='/mnt/models/fastspeech2_aishell3/snapshot_iter_96400.pdz',
                am_stat='/mnt/models/fastspeech2_aishell3/speech_stats.npy',
                phones_dict='/mnt/models/fastspeech2_aishell3/phone_id_map.txt',
                speaker_dict='/mnt/models/fastspeech2_aishell3/speaker_id_map.txt',
                voc='hifigan_aishell3',
                voc_config='/mnt/models/hifigan_aishell3/default.yaml',
                voc_ckpt='/mnt/models/hifigan_aishell3/snapshot_iter_2500000.pdz',
                voc_stat='/mnt/models/hifigan_aishell3/feats_stats.npy',
            )
        print(f"模型加载成功: {model_type}")
        return model

    def get_model(self, spk_id):
        """根据 spk_id 返回对应的模型实例"""
        if spk_id == 1:  # 默认女声
            if 'default' not in self.models:
                self.models['default'] = self._load_model('default')
            return self.models['default'], None
        elif spk_id == 2:  # 男声
            if 'male' not in self.models:
                self.models['male'] = self._load_model('male')
            return self.models['male'], None
        else:  # AISHELL3
            if 'aishell3' not in self.models:
                self.models['aishell3'] = self._load_model('aishell3')
            return self.models['aishell3'], spk_id

# 全局 TTS 管理器
tts_manager = TTSManager()

def deletion_worker():
    """后台定期清理文件"""
    while True:
        if deletion_queue:
            temp_file = deletion_queue.pop(0)
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    print(f"已删除文件: {temp_file}")
            except PermissionError:
                print(f"文件占用中，稍后再试: {temp_file}")
                deletion_queue.append(temp_file)
        time.sleep(1)

# 启动删除线程
threading.Thread(target=deletion_worker, daemon=True).start()

def clear_mp3_files(directory):
    """清理指定目录下的所有.mp3文件"""
    for file in os.listdir(directory):
        if file.endswith(".mp3"):
            try:
                os.remove(os.path.join(directory, file))
                print(f"已删除文件: {file}")
            except Exception as e:
                print(f"删除文件失败: {file}, 原因: {e}")

def generate_audio_task(data):
    global stop_flag

    base_name = data.get("name", "audio_segment")
    raw_text = data.get("text", "你好，欢迎使用PaddleSpeech。")
    spk_id = int(data.get("spk_id", 1))

    sentences = split_text_into_sentences(raw_text)

    audio_files = []
    for i, sentence in enumerate(sentences):
        if stop_flag:  # 检查中断标志
            print("中断音频生成任务")
            return jsonify({"message": "音频生成已被中断"}), 200

        audio_path = os.path.join(output_dir, f"{base_name}_{i:04d}.mp3")
        model, speaker_id = tts_manager.get_model(spk_id)
        if spk_id == 2:  # 男声
            model(
                text=sentence, output=audio_path,
                am='fastspeech2_male', lang='zh',
                phones_dict='/mnt/models/fastspeech2_male_zh/phone_id_map.txt'
            )
        elif spk_id > 2:  # AISHELL3
            model(
                text=sentence, output=audio_path, spk_id=speaker_id,
                am='fastspeech2_aishell3', lang='zh'
            )
        else:  # 默认女声
            model(text=sentence, output=audio_path)
        audio_files.append(audio_path)

    combined_audio_path = os.path.join(files_dir, f"{base_name}.mp3")
    merge_audio_files(audio_files, combined_audio_path)

    deletion_queue.extend(audio_files)

@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    global stop_flag, current_thread

    if current_thread and current_thread.is_alive():
        return jsonify({"error": "已有一个生成任务正在运行"}), 400

    stop_flag = False
    data = request.get_json()
    if not data or 'name' not in data or 'text' not in data:
        return jsonify({"error": "Invalid input. 'name' and 'text' fields are required."}), 400

    clear_mp3_files(output_dir)

    current_thread = threading.Thread(target=generate_audio_task, args=(data,))
    current_thread.start()

    return jsonify({"message": "音频生成任务已开始"}), 200

@app.route('/stop_audio', methods=['POST'])
def stop_audio():
    global stop_flag
    stop_flag = True
    return jsonify({"message": "音频生成中断指令已发送"}), 200

def split_text_into_sentences(text, max_length=30):
    """根据标点符号和最大长度拆分文本"""
    punctuation = r'([。！？\.\!\?，,；;])'
    parts = re.split(punctuation, text)
    sentences, temp_sentence = [], ''
    for part in parts:
        if re.match(punctuation, part):
            temp_sentence += part
            if len(temp_sentence) >= max_length or part in '。！？.\!?':
                sentences.append(temp_sentence.strip())
                temp_sentence = ''
        else:
            temp_sentence += part
            if len(temp_sentence) >= max_length:
                sentences.append(temp_sentence.strip())
                temp_sentence = ''
    if temp_sentence.strip():
        sentences.append(temp_sentence.strip())
    return sentences

def merge_audio_files(input_files, output_file):
    """合并多个音频文件"""
    combined = AudioSegment.empty()
    for file in input_files:
        audio_segment = AudioSegment.from_mp3(file)
        combined += audio_segment
    combined.export(output_file, format="mp3")

@app.route('/files/<path:filename>', methods=['GET'])
def download_file(filename):
    """提供下载接口"""
    return send_from_directory(files_dir, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8888)