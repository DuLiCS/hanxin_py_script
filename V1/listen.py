import os
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 设置音频文件目录为当前工作目录
output_dir = os.getcwd()  # 获取并使用当前工作目录

class AudioFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.file_queue = []

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".mp3"):
            # 将新文件按顺序添加到队列
            self.file_queue.append(event.src_path)
            self.file_queue.sort()  # 按文件名排序，确保顺序播放

    def play_files_in_order(self):
        while True:
            if self.file_queue:
                # 取出第一个文件并使用 ffplay 播放
                audio_file = self.file_queue.pop(0)
                print(f"播放音频文件: {audio_file}")

                # 使用 ffplay 播放音频文件
                subprocess.run(["ffplay", "-nodisp", "-autoexit", audio_file])
            else:
                time.sleep(0.1)  # 如果没有文件等待播放，则稍作延迟

if __name__ == "__main__":
    # 设置文件系统观察者
    event_handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=output_dir, recursive=False)
    observer.start()

    print("开始监听音频文件夹...")
    try:
        # 在主线程中循环播放文件
        event_handler.play_files_in_order()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
