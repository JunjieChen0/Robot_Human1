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

2026-11-18收到[S01的操作记录](../user_test/squat_counter_S01_review.md)与1份侧面剪辑视频；组织者确认同学本人独立完成、视频经过剪辑且符合课程要求。S01自报“部分完成”。原素材来源、剪辑明细和拍摄日期未提供；未明确授权公开影像，视频和含人物截图仅本地保留。具体确认见[组织者记录](../user_test/squat_counter_actor_confirmation.json)，素材SHA256与导出一致。

同日新增[S02记录](../user_test/squat_counter_S02_review.md)和[原素材/计数说明](../user_test/squat_counter_S02_ground_truth_note.txt)，组织者确认另一名同学独立操作及课程使用同意，当前同学记录2/3。来稿称实体拍摄原15秒片段截取前约12.3秒后拼接两次；原片出处、拍摄日期未提供，影像仅本地保存。S02自报“已完成”，同时说明正式导出前有一次清空重试；当前导出只有自动结束。素材哈希一致。

两份输入仅有单一光照外观，尚无三种条件设计及符合预定规则的独立完成事件标注；会话均包含手动暂停，未纳入连续识别性能评分。S02标注仅给最低点与每0.5秒取样，不能当作恢复站立时刻。先前空画面、合成摄像头和模拟关键点检查继续与同学操作分开，不能计为三位真人或真实识别准确率。

后续每份真实片段在`user_test/squat_media_register.csv`记录来源、授权范围与条件。未取得同意的他人影像不纳入，软件许可或公开视频链接不能自动代替影像使用同意。
