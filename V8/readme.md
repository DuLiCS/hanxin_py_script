## 更新


增加了中断。

/stop_audio 接口使用 POST 请求，它不需要传递额外的数据，只需要调用即可触发中断操作。

示例请求

当调用 /stop_audio 时，stop_flag 会被设置为 True，生成任务会检测到并中断操作。

使用 cURL 发送中断请求

curl -X POST http://<your_server_ip>:8888/stop_audio

使用 Python 发送中断请求

import requests

response = requests.post("http://<your_server_ip>:8888/stop_audio")
print(response.json())

前端 JavaScript 示例

fetch('http://<your_server_ip>:8888/stop_audio', {
    method: 'POST'
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error('Error:', error));

服务器逻辑解释

	1.	stop_flag 是一个全局变量：
	•	它的默认值是 False。
	•	在 /stop_audio 接口中，被设置为 True。
	2.	生成任务中定期检查 stop_flag：
	•	在 generate_audio_task 的音频生成循环中，加入了 if stop_flag: 检查。
	•	如果 stop_flag 被设置为 True，任务会提前退出并返回中断信息。

测试

	1.	运行 Flask 服务。
	2.	启动一个音频生成任务。
	3.	在任务运行过程中发送 /stop_audio 请求。
	4.	观察日志输出，确认任务中断。
