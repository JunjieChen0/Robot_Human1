"""Browser-local pose inference and session export, integrated with Streamlit."""

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


FRONTEND = Path(__file__).parent / "squat_frontend"
_counter = components.declare_component("squat_counter", path=str(FRONTEND))


def render_squat_page():
    st.title("深蹲计数")
    st.write("面向大学生的单人侧面计数：完成站立、下蹲、恢复站立，核对反馈并修正误计或漏计。")
    manifest = json.loads((FRONTEND / "asset_manifest.json").read_text(encoding="utf-8"))
    missing = [name for name in manifest["files"] if not (FRONTEND / "vendor" / name).is_file()]
    if missing:
        st.warning("姿态模型资源尚未准备。先运行启动脚本，或执行下方下载命令。")
        st.code("python scripts/download_squat_assets.py")
        return
    _counter(model_sha256=manifest["files"]["pose_landmarker_lite.task"], key="squat_counter")
    with st.expander("计数规则与适用范围"):
        st.write("先确认站立，再下蹲并恢复站立计1次；下蹲保持3秒仍只计1次。膝角≥160°为站立，≤100°为下蹲，各持续300毫秒；中间区间不触发。相邻有效帧间隔超过500毫秒、关键点不清或手动暂停后，须重新确认站立。")
        st.write("这是课堂计数条件，不评价动作是否标准。单人、固定侧面、肩髋膝踝完整入镜；不从深蹲次数推算热量、肥胖等级或健康结论。首次规则尚需真实视频验证。")
        st.caption("squat-counter-v2 · MediaPipe Pose Landmarker Lite · 浏览器CPU推理；模型资源由本地服务提供，原视频和摄像头画面不上传到Python服务。")
