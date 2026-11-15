# 姿态模型与影像来源

## 模型与软件

- 预训练模型：Google MediaPipe Pose Landmarker Lite，`float16/1`，没有使用原肥胖分类模型，也没有在本项目重新训练视觉模型。
- 官方模型说明及模型卡入口：[Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)。模型与其训练数据适用性按官方说明理解，不能据姿态关键点推断健康状况。
- 固定模型URL：`https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`。
- 模型SHA256：`59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`。
- JavaScript SDK：`@mediapipe/tasks-vision@0.10.32`，官方npm registry下载；包声明Apache-2.0许可，版权与许可说明保留在下载资源中。
- `src/squat_frontend/asset_manifest.json`固定SDK压缩包SHA512及各资源SHA256。下载脚本写入前校验，之后复用缓存；浏览器也校验模型SHA256。
- CPU模式在Web Worker运行；不安装Python MediaPipe、OpenCV或GPU运行库。运行速度需按实际客户端测试，不能根据服务器配置承诺实时帧率。

## 本地数据与权限

摄像头由使用者浏览器获取，不是服务器上的摄像头。浏览器需要localhost/HTTPS等安全上下文及使用者授权；远程Linux服务可用SSH端口转发到localhost。关闭、结束或移除页面时停止媒体轨道。参考[浏览器摄像头](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)与[停止媒体轨道](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop)。

原视频与画面默认不上传或录制。导出JSON含视频文件名/哈希、选定侧关键点坐标、角度、计数、修正历史、操作与自报字段，不含视频帧。建议文件名使用匿名编号，组织者仅保存已获同意的课程材料。

## 当前影像证据状态

目前没有纳入真人深蹲视频或三名同学记录。自动检查使用程序生成的纯色空视频，检验真实模型能否返回看不清并不乱计数；另用明确标记的模拟关键点验证计数与纠错控件。这些不能计入识别准确性或真人使用效果。

后续每份真实片段在`user_test/squat_media_register.csv`记录来源、授权范围与条件。未取得同意的他人影像不纳入，软件许可或公开视频链接不能自动代替影像使用同意。
