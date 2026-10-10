import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stdin.reconfigure(encoding="utf-8")

# import os
# #使用国内镜像
# os.environ["HF_ENDPOINT"]="https://hf-mirror.com"

import os
import re
import io
import base64
from PIL import Image
from datetime import datetime
import pandas as pd
import dashscope
from dashscope import MultiModalConversation
import streamlit as st


def reset_question():
    st.session_state.ai_answer = ""
    st.session_state.student_input = ""
    st.rerun()


# ======初始化会话状态=======
if "ai_answer" not in st.session_state:
    st.session_state.ai_answer = ""
if "student_input" not in st.session_state:
    st.session_state.student_input = ""
if "show_short_ans" not in st.session_state:
    st.session_state.show_short_ans = False
if "show_similar" not in st.session_state:
    st.session_state.show_similar = False
if "show_similar_ans" not in st.session_state:
    st.session_state.show_similar_ans = False

if "full_text" not in st.session_state:
    st.session_state.full_text = ""
if "short_text" not in st.session_state:
    st.session_state.short_text = ""
if "similar_text" not in st.session_state:
    st.session_state.similar_text = ""
if "similar_ans_text" not in st.session_state:
    st.session_state.similar_ans_text = ""


# 回调函数
def show_short_answer():
    st.session_state.show_short_ans = True


def show_similar_exercise():
    st.session_state.show_similar = True


def show_similar_answer():
    st.session_state.show_similar_ans = True


def reset_all():
    st.session_state.show_short_ans = False
    st.session_state.show_similar = False
    st.session_state.show_similar_ans = False
    st.session_state.full_text = ""
    st.session_state.short_text = ""
    st.session_state.similar_text = ""
    st.session_state.similar_ans_text = ""
    st.rerun()


# ====限制内容宽度=====
st.markdown("""
<style>
    .block-container {
        max-width: 960px;
        margin: 0 auto;
    }

    p, li {
        line-height: 1.8;
        font-size: 15px;
    }

    h1, h2, h3 {
        margin-top: 20px;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)


# 重置函数：清空答题状态，保留学情记录
def reset_question():
    st.session_state.ai_answer = ""
    st.session_state.student_input = ""
    st.rerun()  # 刷新整个页面


# ====密钥输入框，网页上手动输入=====
api_key = st.text_input("请输入DashScope API密钥", type="password")
if api_key:
    dashscope.api_key = api_key
else:
    st.warning("请输入API密钥才能调用大模型")

import streamlit as st
import os

# 从streamlit后台secrets读取DASHSCOPE_API_KEY
# try:
#     # 线上部署
#     DASHSCOPE_API_KEY = st.secrets["DASHSCOPE_API_KEY"]
# except:
#     # 本地调试时，优先读取环境变量；线上部署走上面st.secrets
#     DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
#
# # 校验密钥是否存在
# if not DASHSCOPE_API_KEY:
#     st.error("API密钥缺失！线上版本请在Secrets配置密钥，本地可设置环境变量。")
#     st.stop()

# # 初始化dashscope
# import dashscope
#
# dashscope.api_key = DASHSCOPE_API_KEY

# # RAG相关导入
# from langchain_community.document_loaders import PyPDFLoader
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_community.vectorstores import Chroma
# from langchain_community.embeddings import HuggingFaceEmbeddings

# ====================== 系统提示词 ======================
SYSTEM_PROMPT = """
你是一名大学线性代数辅导助教，核心目标：帮助学生理解线性代数核心定义、定理与证明，严禁直接给出完整证明答案,严格依据邱维声《高等代数（第四版）》教材内容进行引导。
**优先往前追溯前面学过的基础定义，不使用教材后面章节的知识**。
规则：
1. 学生上传线代证明题，不要直接写出完整证明；采用启发式提问，一步步引导思考。
**先往前回忆本节课之前讲过的基础定义，从已学概念出发，不调用后面才学的知识定理**。
2. 优先聚焦概念：向量、矩阵、秩、线性无关、特征值、子空间、行列式等基础定义。
3. 当学生提交自己的推导证明：
    - 识别概念误解、定理误用、逻辑跳跃；
    - 不直接写完整证明，使用提问引导学生自查；
    - 引用知识库中的定义/定理来指出问题。 
4. 如果学生概念混淆，先回顾对应定义，再引导推理。
5. 回答简洁，分步骤引导，多用提问方式，不要一次性把结论说破。
6. 只回答线性代数相关内容，其他问题礼貌拒绝。
7. 绝对不能直接写出完整证明、最终答案。只提问、提示教材定义，引导学生自己推导。
8. 语言简洁，避免长篇大论。优先引用邱维声教材里的定义、命题、定理。
9. 学生写推导之后，只指出概念错误，用教材原文反问，不直接订正全部步骤。
10. 禁止一次性抛出大量问题，每次只提1~2个简短问题，控制文字长度。

11.在回答学生推导时，最后额外输出三行标记：
【知识点】本题涉及的教材知识点，顿号分隔（如：矩阵的秩、子矩阵、极大无关组）
【混淆】学生是否混淆了某定理/概念，写出具体混淆点，无则写"无"
【不明白】学生推导中暴露出的、尚未掌握的内容，无则写"无"

你是线代启明星，回答线性代数题目严格使用下面固定格式：

输出分为三部分，严格使用标记【---SPLIT1---】、【---SPLIT2---】、【---SPLIT3---】分隔，不要多余文字。

第一部分（完整版，给用户学习）严格格式：
### 题目
抄写原题
### ✅ 核心知识点（整齐罗列，每条简短）
1. 知识点1：一句话简述
2. 知识点2：一句话简述
3. 知识点3：一句话简述

输出规则：
1. 每一条知识点/要点，必须使用【1. 2. 3.】有序列表，每一条写完必须换行，**全部顶格写，不要首行缩进**。
2. 不要写大段连在一起的长文本，一条要点单独一行，分段中间隔两行再写下一段。
3. 不要用>引用块（引用块会自带缩进）。
4. 不要在开头加空格、Tab。


### 📝 解题/证明过程
分步书写，每一步标注依据，公式规范，逻辑清晰
### 📋 最终总结
一句话总结本题核心结论与解题思路

【---SPLIT1---】

第二部分（精简抄写版，按钮触发展示）：
只保留作业可以直接抄写的解题/证明步骤，不要知识点、不要总结、不要多余解释，公式规范。

【---SPLIT2---】

第三部分（举一反三同类练习题）：
输出**2道**同考点、同思路、变式练习题，每道题前面标注难度【简单/中等/难题】。
只写题目，不写答案，用来给学生自主练习巩固。
标题：📚 举一反三 · 同类变式练习题


【---SPLIT3---】

第四部分（变式题参考答案）：
对应上面2道练习题，给出完整解答，公式规范。
标题：✅ 变式题参考答案


最后输出：🔘【点击整理精简答案】
当用户点击【点击整理精简答案】后，输出精简版答案，去掉知识点罗列，只保留可直接抄写的解题/证明步骤。

要求：知识点只写本题用到的，不要冗余；步骤严谨，符合大学线性代数作业书写规范。

输出禁止使用<和>尖括号，不要输出任何HTML标签。向量、矩阵不要用尖括号表示。



请用清晰的 Markdown 格式输出，不要使用 < > 尖括号，不要输出任何 HTML 标签。


"""


# ========== 处理用户提问 ==========
# 输入框，把用户输入保存到 user_input 变量
user_input = st.text_area("请输入你的线代问题：", height=180)

if user_input:
    # 只调用一次大模型
    resp = dashscope.Generation.call(
        model="qwen-turbo",
        temperature=0.1,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ],
        result_format="message"
    )

    total_content = resp.output.choices[0].message.content


    # 排版美化
    total_content = re.sub(r'<.*?>', '', total_content)
    total_content = re.sub(r'(?<!\n)(\d+\. )', r'\n\n\1', total_content)
    total_content = re.sub(r'。', r'。\n\n', total_content)
    total_content = "# 📘 线性代数解答\n\n" + total_content

    st.subheader("📘 结果展示")
    with st.expander("📖 查看完整解答", expanded=True):
        st.markdown(total_content, unsafe_allow_html=False)

    # =========过滤尖括号，解决浏览器报错========
    import re

    total_content = re.sub(r'<.*?>', '', total_content)

    st.subheader("📘 完整解答")
    with st.container():
        st.markdown(total_content, unsafe_allow_html=False)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("✅ 精简答案")
        st.info(short_part if 'short_part' in locals() else "暂无")

    with col2:
        st.subheader("🔁 同类题思路")
        st.warning(similar_part if 'similar_part' in locals() else "暂无")

    # 容错分割四段内容
    part1 = total_content.split("【---SPLIT1---】")
    if len(part1) >= 2:
        full_part = part1[0].strip()
        remain = part1[1]
        part2 = remain.split("【---SPLIT2---】")
        if len(part2) >= 2:
            short_part = part2[0].strip()
            similar_part = part2[1].strip()
        else:
            short_part = remain
            similar_part = "⚠️ 变式练习题生成失败，请重新提问"
    else:
        full_part = total_content
        short_part = "⚠️ 精简答案生成失败，请重新提问"
        similar_part = "⚠️ 变式练习题生成失败，请重新提问"

    # 存入session_state
    st.session_state.full_text = full_part
    st.session_state.short_text = short_part
    st.session_state.similar_text = similar_part
    st.session_state.show_short_ans = False
    st.session_state.show_similar = False

    # 展示完整版解析
    with st.chat_message("assistant"):
        st.markdown(st.session_state.full_text)

    # 并排两个功能按钮
    col1, col2 = st.columns(2)
    with col1:
        st.button("📝 点击整理精简答案（作业抄写版）",
                  on_click=show_short_answer,
                  type="primary",
                  use_container_width=True)
    with col2:
        st.button("📚 举一反三，查看同类练习题",
                  on_click=show_similar_exercise,
                  use_container_width=True)
    # 在每一条有序列表前增加换行，强制分段
    total_content = re.sub(r'<.*?>', '', total_content)
    total_content = re.sub(r'(?<!\n)(\d+\. )', r'\n\n\1', total_content)
    # 渲染
    st.subheader("📘 线性代数解答")
    with st.expander("📘 查看完整解答", expanded=True):
        st.markdown(total_content, unsafe_allow_html=False)




# 展示精简答案
if st.session_state.full_text != "" and st.session_state.show_short_ans:
    st.divider()
    st.subheader("✅ 精简抄写版答案")
    st.markdown(st.session_state.short_text)

# 展示变式练习题 + 【查看变式题答案】按钮
if st.session_state.full_text != "" and st.session_state.show_similar:
    st.divider()
    st.subheader("📚 举一反三 · 同类变式练习题")
    st.markdown(st.session_state.similar_text)
    st.button("📖 查看变式题答案", on_click=show_similar_answer, use_container_width=True)

# 展示变式题参考答案
if st.session_state.full_text != "" and st.session_state.show_similar_ans:
    st.divider()
    st.subheader("✅ 变式题参考答案")
    st.markdown(st.session_state.similar_ans_text)

# 重置按钮
if st.session_state.full_text != "":
    st.button("🔄 重置，开始下一题", on_click=reset_all)

# ======缓存变量，保存图片解析的AI引导内容=====
ai_guide_result = ""
question_desc = ""

# ====================== RAG知识库配置 ======================
# PERSIST_DIR = "./chroma_db"
# embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
# text_splitter = RecursiveCharacterTextSplitter(
#    chunk_size=500,
#     chunk_overlap=100,
#     separators=["\n\n", "\n", "。", "；"]
# )
#
# if os.path.exists(PERSIST_DIR):
#     vector_db = Chroma(persist_directory=PERSIST_DIR, embedding_function=embedding_model)
# else:
#     vector_db = Chroma(embedding_function=embedding_model, persist_directory=PERSIST_DIR)
#
# # 检索函数
# def search_knowledge(query, top_k=2):
#     docs = vector_db.similarity_search(query, k=top_k)
#     content = "\n".join([doc.page_content for doc in docs])
#     return content


# ========== 学情保存：只记知识点与混淆点，不记启发式引导 ==========
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import datetime

EXCEL_FILE = "student_learning_record.xlsx"

import re

# 初始化默认值，防止提取失败时报错
ai_knowledge_points = []
ai_confused_theorem = "无"
ai_unclear_point = "无"

# =========【提交按钮】=========
if st.button("提交作答，获取AI诊断"):
    # 1.调用大模型，返回结果赋值resp
    resp = 你的大模型请求函数(图片, 学生输入)

    # 2. 在这里写正则提取！！放在if里面，resp已经有值
    import re

    ai_knowledge_points = []
    ai_confused_theorem = "无"
    ai_unclear_point = "无"

    match_kp = re.search(r"【知识点】(.*?)(?=【|$)", resp, re.S)
    match_confuse = re.search(r"【混淆】(.*?)(?=【|$)", resp, re.S)
    match_unclear = re.search(r"【不明白】(.*?)(?=【|$)", resp, re.S)

    if match_kp:
        kp_text = match_kp.group(1).strip()
        ai_knowledge_points = kp_text.split("、")
    if match_confuse:
        ai_confused_theorem = match_confuse.group(1).strip()
    if match_unclear:
        ai_unclear_point = match_unclear.group(1).strip()

    # 3. 学情保存，同样在if内部
    save_learning_record(
        student_name=student_name,
        student_id=student_id,
        knowledge_points=ai_knowledge_points,
        theorem_confused=ai_confused_theorem,
        unclear_point=ai_unclear_point,
        answer_status="引导后完成"
    )


def save_learning_record(student_name, student_id, knowledge_points, theorem_confused, unclear_point, answer_status):
    """
    knowledge_points : 本题涉及的知识点列表，如 ["矩阵的秩", "子矩阵", "极大无关组"]
    theorem_confused : 定理是否混淆，如 "秩不等式混淆" 或 ""
    unclear_point    : 不明白/卡住的内容，如 "分块矩阵初等变换没掌握"
    answer_status    : 作答结果，如 "引导后完成" / "未完成"
    """
    # 若文件不存在，先建表头
    if not os.path.exists(EXCEL_FILE):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "学情记录"
        headers = ["学生姓名", "学号", "涉及知识点", "定理混淆", "不明白的内容", "作答状态", "记录时间"]
        ws.append(headers)
        wb.save(EXCEL_FILE)

    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb["学情记录"]

    # 一条记录一行；知识点用顿号/分号拼接
    kp_str = "、".join(knowledge_points) if isinstance(knowledge_points, list) else str(knowledge_points)
    new_row = [student_name, student_id, kp_str, theorem_confused or "无", unclear_point or "无", answer_status,
               datetime.now().strftime("%Y-%m-%d %H:%M")]
    ws.append(new_row)

    beautify_sheet(ws)
    wb.save(EXCEL_FILE)


# ========美化excel表格函数========
def beautify_sheet(ws):
    # 表头样式
    header_fill = PatternFill("solid", fgColor="4472C4")  # 蓝色表头
    header_font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # 表头行处理
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 数据行：边框 + 自动换行 + 顶部对齐
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    # 奇偶行交替底色（更美观）
    row_fill = PatternFill("solid", fgColor="D9EAF7")  # 浅蓝
    for i, row in enumerate(ws.iter_rows(min_row=2), start=0):
        if i % 2 == 1:
            for cell in row:
                cell.fill = row_fill

    # 列宽按内容设置
    widths = {"A": 10, "B": 12, "C": 40, "D": 22, "E": 32, "F": 14, "G": 18}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # 冻结表头（滚动时表头固定）
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 24


# ====================== Streamlit页面开始 ======================
import streamlit as st

st.set_page_config(page_title="线代启明星", layout="wide")
st.markdown("<h1 style='color:#1F3864;'>线代启明星｜启真问智大赛</h1>", unsafe_allow_html=True)

# =============页面最底部下一题按钮============
st.divider()
if st.button("下一题（重置答题）"):
    reset_question()
    # 清空session，重置页面
    st.session_state["img_upload"] = None
    st.session_state["student_input"] = ""
    st.rerun()

# 美化上传框CSS，支持拖拽
custom_css = """
<style>
/* 整体字体更清晰 */
html, body, [class*="css"] {
    font-family: "Microsoft YaHei", "SimHei", Arial, sans-serif;
    color: #222222;
}

/* 主标题蓝色 */
h1 {
    color: #1F3864;
    font-weight: bold;
}

/* 二级标题蓝色 */
h2 {
    color: #1F3864;
    font-weight: bold;
    border-left: 5px solid #2E75B6;
    padding-left: 12px;
}

/* 三级标题蓝色 */
h3 {
    color: #2E75B6;
    font-weight: bold;
}

/* 正文黑色 */
p, div, span, label {
    color: #222222;
}

/* 输入框文字黑色 */
textarea, input {
    color: #222222 !important;
}

/* 分割线更明显 */
hr {
    border: none;
    border-top: 2px solid #D9E2F3;
    margin-top: 24px;
    margin-bottom: 24px;
}

/* 上传框蓝色边框 */
[data-testid="stFileUploader"] {
    border: 2px solid #2E75B6 !important;
    border-radius: 10px !important;
    padding: 18px !important;
    background-color: #F7FAFF !important;
}

/* 按钮蓝色 */
.stButton > button {
    background-color: #2E75B6 !important;
    color: white !important;
    border-radius: 8px !important;
    font-weight: bold !important;
    border: none !important;
}

.stButton > button:hover {
    background-color: #1F3864 !important;
    color: white !important;
}

/* 成功信息蓝色 */
.stSuccess {
    background-color: #EAF3FF !important;
    color: #1F3864 !important;
    border-left: 5px solid #2E75B6 !important;
}

/* 提示信息蓝色 */
.stInfo {
    background-color: #EAF3FF !important;
    color: #1F3864 !important;
    border-left: 5px solid #2E75B6 !important;
}

/* 警告信息黑色蓝色 */
.stWarning {
    background-color: #FFF8E1 !important;
    color: #1F3864 !important;
    border-left: 5px solid #FFB020 !important;
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# -------- RAG知识库上传区域 --------
st.subheader("上传线性代数PDF知识库（讲义/定理）")
pdf_file = st.file_uploader("上传PDF文件", type=["pdf"], key="pdf_upload")
if pdf_file is not None:
    with open("temp_linealgebra.pdf", "wb") as f:
        f.write(pdf_file.read())
    loader = PyPDFLoader("temp_linealgebra.pdf")
    pages = loader.load_and_split()
    split_docs = text_splitter.split_documents(pages)
    vector_db.add_documents(split_docs)
    vector_db.persist()
    st.success("✅PDF知识库导入完成！已存入向量库")

st.divider()

# -------- 图片上传与题目AI引导 --------
st.subheader("上传线性代数证明题图片（可直接拖拽图片到框内）")
uploaded_file = st.file_uploader(
    "直接把照片拖入此处，或者点击Upload上传 | 200MB · JPG, PNG",
    type=["jpg", "png"],
    key="img_upload"
)

if uploaded_file is not None:
    img = Image.open(uploaded_file)

    # ========== 网页预览用缩小图，不影响AI识别 ==========
    preview_img = img.copy()
    max_w = 400
    if preview_img.width > max_w:
        ratio = max_w / preview_img.width
        new_h = int(preview_img.height * ratio)
        preview_img = preview_img.resize((max_w, new_h))
    st.image(preview_img, caption="题目图片（预览缩小）")

    # ========== 下面base64部分保持原样，使用原始img，保证识别清晰度 ==========
    buf = io.BytesIO()
    # 如果是RGBA带透明通道，先转RGB
    if img.mode == "RGBA":
        img = img.convert("RGB")
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()
    base64_str = base64.b64encode(img_bytes).decode()

    # RAG检索
    question_text = "这道线性代数证明题，需要用到哪些定理定义"
    # rag_context = search_knowledge(question_text)
    rag_context = ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": f"data:image/jpeg;base64,{base64_str}"},
                {"type": "text", "text": f"""
参考下面教材知识库内容：
{rag_context}
学生后续会输入自己的证明思路，请做好准备。
请分析这道线性代数题目，用简短一句话概括题目，然后启发式引导思考，不要直接写完证明。
"""}
            ]
        }
    ]

    with st.spinner("正在识别题目，生成引导思路..."):
        response = MultiModalConversation.call(
            model="qwen3-vl-plus",
            messages=messages,
            stream=False
        )
    if response.status_code == 200:
        ai_text = response.output.choices[0].message.content
        ai_guide_result = ai_text[0]["text"]
        st.subheader("AI辅导回复")
        # 去掉表情包和杂乱符号，改成黑色正文、蓝色小标题
        import re


        def clean_ai_text(text):
            # 删除表情包和特殊符号
            text = re.sub(
                r"[^\w\s，。！？、；：()（）\-\—\[\]{}<>=≠≤≥±×÷∑∏∫√∂∇∈∉∋∌∩∪⊂⊃⊄⊅⊆⊇⊈⊉⊊⊋⊥∥∠°παβγδεζηθλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]+",
                "", text)
            # 合并多余空行
            text = re.sub(r"\n{2,}", "\n", text)
            return text.strip()


        clean_guide = clean_ai_text(ai_guide_result)
        st.markdown(f"<h3 style='color:#1F3864;'>AI题目引导</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#222222;line-height:1.8;'>{clean_guide}</p >", unsafe_allow_html=True)
        # 截取前80字作为题目简述
        question_desc = ai_guide_result[:80]
    else:
        st.error(f"调用失败！{response.message}")

st.divider()

# -------- 学生推导输入 & 批改模块 --------
st.subheader("✍ 写下你的推导/证明思路")
student_reason = st.text_area("把你的思考过程写在这里，AI结合知识库帮你检查概念错误", height=150, key="student_text")

check_btn = st.button(" 检查我的推导（检索知识库）")
if check_btn and student_reason.strip() != "":
    # rag_student_context = search_knowledge(student_reason)
    rag_student_context = ""  # 先跳过检索函数
    resp_student = MultiModalConversation.call(
        model="qwen3-vl-plus",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"""
参考教材知识库内容：
{rag_student_context}
学生的推导：{student_reason}
任务：检查学生线性代数证明思路，找出概念错误、逻辑缺口。
不要直接给出完整证明。用启发式提问，指出哪里定义理解出错，提示对应的定理。
"""}
                ]
            }
        ],
        stream=False
    )
    if resp_student.status_code == 200:
        student_check_result = resp_student.output.choices[0].message.content
        ai_check_text = student_check_result[0]["text"]
        st.write("###  辅导反馈")
        clean_check = clean_ai_text(ai_check_text)
        st.markdown(f"<h3 style='color:#1F3864;'>AI推导批改反馈</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#222222;line-height:1.8;'>{clean_check}</p >", unsafe_allow_html=True)

        # 自动保存学情
        save_study_record(question_desc, student_reason, ai_guide_result, ai_check_text)
        st.success("✅ 本次学习记录已自动保存到【学情记录.xlsx】！")
    else:
        st.error(f"批改调用失败：{resp_student.message}")

# 备用手动保存按钮
st.divider()
if st.button(" 手动保存当前记录（备用）"):
    if ai_guide_result and student_reason:
        save_study_record(question_desc, student_reason, ai_guide_result, "手动保存，无批改反馈")
        st.success("✅手动保存成功")
    else:
        st.warning("请先上传题目或者填写推导内容")

st.divider()

# ========== 教师学情查看面板 ==========
st.subheader(" 教师学情查看面板")
st.info("教师可直接查看全部学生学习记录，无需打开Excel文件")

file_name = "学情记录.xlsx"
if os.path.exists(file_name):
    df_all = pd.read_excel(file_name)
    st.dataframe(df_all, use_container_width=True)

    record_options = df_all["记录时间"].tolist()
    selected_time = st.selectbox("选择一条记录，查看完整详情", record_options)
    selected_row = df_all[df_all["记录时间"] == selected_time].iloc[0]

    st.markdown("####  本条记录详情")
    st.write(f"**记录时间：** {selected_row['记录时间']}")
    st.write(f"**题目简述：** {selected_row['题目简述']}")
    st.write(f"**学生推导：**")
    st.text_area("", value=selected_row["学生推导"], height=120, disabled=True)
    st.write(f"**AI题目引导回复：**")
    st.text_area("", value=selected_row["AI题目引导回复"], height=120, disabled=True)
    st.write(f"**A**")








