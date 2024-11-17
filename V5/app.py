from flask import Flask, request, jsonify, send_from_directory
from paddlespeech.cli.tts import TTSExecutor
from flask_cors import CORS
from pydub import AudioSegment
import os
import re
import time
import threading
import io

app = Flask(__name__)
CORS(app)  # 启用跨域支持

output_dir = "/mnt"
files_dir = os.path.join(output_dir, "files")  # 存放合并文件的目录
os.makedirs(files_dir, exist_ok=True)  # 确保文件夹存在

deletion_queue = []  # 等待删除的文件队列

class TTSManager:
    """管理不同的 TTS 模型实例"""
    def __init__(self):
        self.models = {}
        self._load_models()

    def _load_models(self):
        """预加载所有模型"""
        print("正在预加载模型...")
        # 默认模型（标准女声）
        self.models['default'] = TTSExecutor()
        self._preload_model(self.models['default'], text="预加载")

        # 男声模型
        self.models['male'] = TTSExecutor()
        self._preload_model(
            self.models['male'],
            text="预加载",
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

        # AISHELL3 模型
        self.models['aishell3'] = TTSExecutor()
        self._preload_model(
            self.models['aishell3'],
            text="预加载",
            spk_id=3,
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
        print("模型预加载完成")

    def _preload_model(self, model, **kwargs):
        """加载模型并生成数据到内存"""
        try:
            # 使用内存中的临时缓冲区
            wav_buffer = io.BytesIO()
            model(
                output=wav_buffer,  # 输出到内存
                **kwargs
            )
            print(f"模型预加载成功：{kwargs.get('am', 'default')}")
        except Exception as e:
            print(f"模型预加载失败：{kwargs.get('am', 'default')}，错误信息：{str(e)}")

    def get_model(self, spk_id):
        """根据 spk_id 返回对应的模型实例"""
        if spk_id == 1:
            return self.models['default']
        elif spk_id == 2:
            return self.models['male']
        else:
            return self.models['aishell3']

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

@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    try:
        data = request.get_json()
        if not data or 'name' not in data or 'text' not in data:
            return jsonify({"error": "Invalid input. 'name' and 'text' fields are required."}), 400

        base_name = data.get("name", "audio_segment")
        raw_text = data.get("text", "你好，欢迎使用PaddleSpeech。")
        spk_id = int(data.get("spk_id", 1))

        # 分割长文本
        sentences = split_text_into_sentences(raw_text)

        # 生成音频
        audio_files = []
        for i, sentence in enumerate(sentences):
            audio_path = os.path.join(output_dir, f"{base_name}_{i:04d}.mp3")
            model = tts_manager.get_model(spk_id)
            if spk_id == 2:  # 男声
                model(
                    text=sentence, output=audio_path,
                    am='fastspeech2_male', lang='zh',
                    phones_dict='/mnt/models/fastspeech2_male_zh/phone_id_map.txt'
                )
            elif spk_id > 2:  # AISHELL3
                model(
                    text=sentence, output=audio_path, spk_id=spk_id,
                    am='fastspeech2_aishell3', lang='zh'
                )
            else:  # 默认女声
                model(text=sentence, output=audio_path)
            audio_files.append(audio_path)

        # 合并音频
        combined_audio_path = os.path.join(files_dir, f"{base_name}.mp3")
        merge_audio_files(audio_files, combined_audio_path)

        deletion_queue.extend(audio_files)  # 添加生成的分段文件到删除队列
        return jsonify({"message": "音频生成成功", "combined_file_url": f"/files/{base_name}.mp3"}), 200

    except Exception as e:
        return jsonify({"error": "音频生成失败", "details": str(e)}), 500

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