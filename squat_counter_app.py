"""Standalone entry for the squat-counter assignment, without health-model dependencies."""

import streamlit as st

from src.squat_ui import render_squat_page


st.set_page_config(page_title="深蹲计数 · WeightTrend", page_icon="🏃", layout="wide")
render_squat_page()
