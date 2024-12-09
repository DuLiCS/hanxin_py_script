import os
import time
import subprocess
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from tkinter import messagebox
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw

class AudioFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.file_queue = []

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".mp3"):
            self.file_queue.append(event.src_path)
            self.file_queue.sort()

    def play_files_in_order(self):
        while True:
            if self.file_queue:
                audio_file = self.file_queue.pop(0)
                print(f"播放音频文件: {audio_file}")

                # 使用 subprocess 运行 ffplay 并防止命令行窗口弹出
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", audio_file],
                    creationflags=subprocess.CREATE_NO_WINDOW  # 不显示命令行窗口
                )
            else:
                time.sleep(0.1)


def start_observer():
    output_dir = os.getcwd()
    event_handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=output_dir, recursive=False)
    observer.start()
    try:
        event_handler.play_files_in_order()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def create_tray_icon():
    def quit_program(icon, item):
        icon.stop()
        os._exit(0)

    # 使用自己的 .ico 文件
    icon_path = os.path.join(os.getcwd(), "hanxin.ico")  # 确保 hanxin.ico 在当前目录
    icon_image = Image.open(icon_path)  # 加载图标

    menu = Menu(MenuItem("退出", quit_program))
    icon = Icon("AudioPlayer", icon_image, "汉鑫软件播放程序", menu)
    icon.run()



if __name__ == "__main__":
    threading.Thread(target=start_observer, daemon=True).start()
    create_tray_icon()
