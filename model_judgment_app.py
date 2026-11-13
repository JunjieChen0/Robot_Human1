"""同学测试专用入口：仅读取冻结实验，无需本地模型或训练数据。"""

import streamlit as st

from src.model_judgment_ui import render_model_judgment_page


st.set_page_config(page_title="模型判断 · 同学测试", page_icon="🔎", layout="wide")
st.markdown("""
<style>
.block-container { padding-top: 2rem; padding-bottom: 3rem; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
    font-size: 1rem !important; color: #465366 !important; opacity: 1 !important;
}
button { min-height: 44px !important; }
button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible,
[role="combobox"]:focus-visible { outline: 3px solid #174ea6; outline-offset: 3px; }
</style>
""", unsafe_allow_html=True)
render_model_judgment_page()
