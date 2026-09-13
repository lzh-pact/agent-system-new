"""Streamlit 前端（模块 F，FR-06）。

页面：知识入库 / 智能问答 / 内容生成 / 数据管道可视化；
侧边栏提供「会话管理」（新建 / 切换），各会话上下文相互隔离（G-4）。

运行方式（先 cd 到项目根目录）：
    pip install streamlit
    python -m streamlit run frontend/app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 保证可从项目根目录导入各模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from service import get_system  # noqa: E402
from data_pipeline.loader import load_records  # noqa: E402

st.set_page_config(page_title="智能 AI Agent 售前服务系统", layout="wide")


@st.cache_resource
def _system():
    return get_system()


sys_ = _system()


def _render_session_manager() -> str:
    """侧边栏会话管理：新建 / 切换，返回当前会话 ID。"""
    st.subheader("会话管理")
    if st.button("＋ 新建会话"):
        new = sys_.create_session()
        st.session_state["session_box"] = new.session_id
        st.rerun()

    sessions = sys_.list_sessions()
    if not sessions:
        sys_.create_session()
        sessions = sys_.list_sessions()

    ids = [s.session_id for s in sessions]
    # 当前选中值持久化到 session_box；默认选最近创建的会话
    if "session_box" not in st.session_state or st.session_state["session_box"] not in ids:
        st.session_state["session_box"] = ids[-1]

    st.selectbox(
        "切换会话",
        ids,
        format_func=lambda sid: sid[:8] + "…",
        key="session_box",
    )
    return st.session_state["session_box"]


st.title("智能 AI Agent 售前服务系统")
with st.sidebar:
    page = st.sidebar.radio(
        "功能",
        ["知识入库", "智能问答", "内容生成", "数据管道可视化"],
    )
    st.divider()
    current_session = _render_session_manager()

if page == "知识入库":
    st.header("知识入库（文档切片 → 双路索引）")
    if st.button("一键载入示例知识库（4 篇产品/售后文档）"):
        from demo import sample_knowledge
        docs = sample_knowledge()
        total = sum(sys_.ingest_doc(title, content) for title, content in docs)
        st.success(f"已载入 {len(docs)} 篇文档，共 {total} 个切片。现在可以去「智能问答」提问了。")
    title = st.text_input("文档标题")
    content = st.text_area("文档内容", height=200)
    if st.button("入库") and title and content:
        n = sys_.ingest_doc(title, content)
        st.success(f"已入库，切分为 {n} 个切片")
    query = st.text_input("检索验证", key="q1")
    if st.button("检索", key="b1") and query:
        for r in sys_.search(query):
            st.markdown(f"**rank {r.rank}**（final={r.final_score:.3f}）: {r.text}")

elif page == "智能问答":
    st.header("售前咨询 Agent（ReAct）")
    st.caption(f"当前会话：`{current_session[:8]}…`（会话隔离）")

    # 展示当前会话历史，验证多轮上下文
    for m in sys_.session_history(current_session):
        who = "🧑 用户" if m.role.value == "user" else "🤖 客服"
        with st.chat_message(m.role.value):
            st.write(m.content)

    query = st.chat_input("你的问题", key="qa_input")
    if query:
        ans = sys_.ask(current_session, query)
        if ans.degraded:
            st.warning(ans.answer)
        else:
            st.success(ans.answer)
        st.caption(f"trace: {' → '.join(t['stage'] for t in ans.trace)}")
        if ans.source_chunks:
            with st.expander("引用来源"):
                for c in ans.source_chunks[:3]:
                    st.write(f"- {c.text}")

elif page == "内容生成":
    st.header("内容生成 Agent（选题/文案/脚本）")
    product_id = st.selectbox("产品", ["P001", "P002", "P003"])
    stage = st.selectbox("阶段", ["all", "topic", "copy", "script"])
    if st.button("生成"):
        results = sys_.generate_content(current_session, {"product_id": product_id, "name": {
            "P001": "智能门锁 S1", "P002": "扫地机器人 R3", "P003": "智能音箱 M2",
        }[product_id]}, stage)
        for gc in results:
            st.markdown(f"### {gc.stage.value}（{gc.status.value}）")
            st.text(gc.content or "（阶段失败，已跳过）")

else:
    st.header("数据脱敏管道可视化")
    uploaded = st.file_uploader("上传原始客服数据（CSV/JSON）", type=["csv", "json", "jsonl"])
    if st.button("运行示例管道"):
        from demo import sample_records
        records = sample_records()
        masked, report = sys_.process_data(records)
        st.subheader("脱敏报告")
        st.json(json.loads(json.dumps(report, default=str)))
        st.subheader("脱敏后样本")
        st.dataframe(masked[:5])
    elif uploaded is not None:
        import tempfile
        with tempfile.NamedTemporaryFile("wb", suffix=Path(uploaded.name).suffix, delete=False) as f:
            f.write(uploaded.getvalue())
            path = f.name
        records = load_records(path)
        masked, report = sys_.process_data(records)
        st.json(json.loads(json.dumps(report, default=str)))
        st.dataframe(masked[:20])