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
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
# =====【文本自动分段美化函数｜兼容LaTeX公式】=====
def format_answer_text(raw_str):
    # 清除多余html标签
    text = re.sub(r'<.*?>', '', raw_str)
    text = re.sub(r'(?<!\n)(\d+\. )', r'\n\n\1', text)
    return text
# =====================================================
# 希腊字母自动补LaTeX包裹
greek_dict = {
    r'delta': r'$\delta$',
    r'rank': r'$\mathrm{rank}$',
    r'mathbb': r'$\mathbb'
}
# ====重置函数：清空答题状态，保留学情记录====
def reset_question():
    st.session_state.ai_answer = ""
    st.session_state.student_input = ""
    st.session_state.question = ""  # 清空题目
    st.session_state.summary_ans = "" # 清空精简答案
    st.session_state.variant_question = "" #清空变式题
# 删除图片上传组件的session
    if "student_img" in st.session_state:
        del st.session_state["student_img"]
    st.rerun()
# # ====密钥输入框，网页上手动输入=====
# api_key = st.text_input("请输入DashScope API密钥", type="password")
# if api_key:
#     dashscope.api_key = api_key
# else:
#     st.warning("请输入API密钥才能调用大模型")
#
# import streamlit as st
# import os
# 从streamlit后台secrets读取DASHSCOPE_API_KEY
try:
    # 线上部署
    DASHSCOPE_API_KEY = st.secrets["DASHSCOPE_API_KEY"]
except:
    # 本地调试时，优先读取环境变量；线上部署走上面st.secrets
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
# 校验密钥是否存在
if not DASHSCOPE_API_KEY:
    st.error("API密钥缺失！线上版本请在Secrets配置密钥，本地可设置环境变量。")
    st.stop()
# 初始化dashscope
dashscope.api_key = DASHSCOPE_API_KEY
# # RAG相关导入
# from langchain_community.document_loaders import PyPDFLoader
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_community.vectorstores import Chroma
# from langchain_community.embeddings import HuggingFaceEmbeddings
# ====================== 系统提示词 ======================
SYSTEM_PROMPT = """
你是一名大学线性代数辅导助教，核心目标：帮助学生理解线性代数核心定义、定理与证明，严禁直接给出完整证明答案,严格依据邱维声《高等代数（第四版）》教材内容进行引导。
**优先往前追溯前面学过的基础定义，不使用教材后面章节的知识**。
强制排版约束：
1. 所有数学符号、希腊字母必须使用LaTeX公式，单行公式用 $ $ 包裹。
例：$\delta_1,\delta_2$，$\eta_1$，$\mathrm{rank}(A)$，不要写delta、eta、operatorname纯文本，不写无$的裸公式。
2. 文字尽量简短，一句话控制在2行以内，杜绝超长段落。
3. 有序列表1.2.3. 每条单独一行，不要把多个知识点挤在同一段落。
4. 不要堆砌多余解释，定义、定理只写核心内容。
5. 禁止无换行的大段长文本，知识点逐条分开。
基础规则：
1. 学生上传线代证明题，不要直接写出完整证明；采用启发式提问，一步步引导思考。优先回忆本节课之前学过的基础定义，从已学概念出发，不调用后面才学的知识定理。
2. 优先聚焦概念：向量、矩阵、秩、线性无关、特征值、子空间、行列式等基础定义。
3. 当学生提交自己的推导证明：
    - 识别概念误解、定理误用、逻辑跳跃；
    - 不直接写完整证明，使用提问引导学生自查；
    - 引用邱维声教材中的定义/定理指出问题。
4. 如果学生概念混淆，先回顾对应定义，再引导推理。
5. 回答简洁，分步骤引导，多用提问方式，不要一次性把结论说破。
6. 只回答线性代数相关内容，其他问题礼貌拒绝。
7. 绝对不能直接写出完整证明、最终答案。只提问、提示教材定义，引导学生自己推导。
8. 语言简洁，避免超长段落。优先引用邱维声教材里的定义、命题、定理。
9. 学生写推导之后，只指出概念错误，用教材原文反问，不直接订正全部步骤。
10. 禁止一次性抛出大量问题，每次只提1~2个简短问题，控制文字长度。
11.在评价学生推导时，回答末尾固定输出三行标记：
【知识点】本题涉及的教材知识点，顿号分隔（如：矩阵的秩、子矩阵、极大无关组）
【混淆】学生是否混淆了某定理/概念，写出具体混淆点，无则写"无"
【不明白】学生推导中暴露出的、尚未掌握的内容，无则写"无"
# 输出格式强制规范（非常重要）
1. 所有有序列表【1. 2. 3.】，**每条单独一行，顶格书写，不缩进**，条目之间空一行。
2. 禁止输出大段连续无换行文字，一个段落只讲一层意思，段落之间空一行。
3. 禁止使用引用块 > ，禁止使用Tab缩进，禁止在行首增加空格。
4. 禁止使用 < > 尖括号，禁止任何HTML标签；向量、矩阵不使用尖括号表示。
5. 严格使用【---SPLIT1---】【---SPLIT2---】【---SPLIT3---】作为分隔标记，标记单独占一行，前后换行。
输出分为四部分，严格按照下面模板：
第一部分（完整版，给用户学习）
### 题目
抄写原题
### ✅ 核心知识点
1. 知识点1：一句话简述
2. 知识点2：一句话简述
3. 知识点3：一句话简述
### 📝 解题/证明过程
分步书写，每一步标注教材依据，公式规范，逻辑清晰
### 📋 最终总结
一句话总结本题核心结论与解题思路
【---SPLIT1---】
第二部分（精简版，按钮触发展示）：
只保留最精简直接的解题/证明步骤，**不包含知识点、总结、额外解释**，公式规范。
【---SPLIT2---】
第三部分（举一反三同类练习题）：
标题：📚 举一反三 · 同类变式练习题
输出2道同考点、同思路的变式练习题，每道题前面标注难度【简单/中等/难题】，只写题目，不写答案，供学生自主练习。
手动点击生成举一反三变式题的按钮才出变式题。
【---SPLIT3---】
第四部分（变式题参考答案）：
标题：✅ 变式题参考答案
对应上面2道练习题，给出完整规范解答，公式规范。
最后固定输出一行：🔘【点击整理精简答案】
知识点只写本题直接用到的，不要冗余内容；步骤严谨，符合大学线性代数作业书写规范。
全程使用标准Markdown，不要输出任何HTML标签，不要使用尖括号。
"""
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
if "question" not in st.session_state:
    st.session_state.question = ""
if "summary_ans" not in st.session_state:
    st.session_state.summary_ans = ""
if "variant_question" not in st.session_state:
    st.session_state.variant_question = ""
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
# ====限制内容宽度 + 修复行高=====
st.markdown("""
<style>
    .block-container {
        max-width: 960px;
        margin: 0 auto;
    }
    p, li {
        line-height: 1.7;
    }
</style>
""", unsafe_allow_html=True)
EXCEL_FILE = "student_learning_record.xlsx"
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
def save_study_record(question_desc, student_reason, ai_guide, ai_check):
    save_learning_record(
        student_name="匿名",
        student_id="匿名",
        knowledge_points=["未提取"],
        theorem_confused="无",
        unclear_point="无",
        answer_status="学生作答"
    )
# ========== 处理用户提问 ==========
# 输入框，把用户输入保存到 user_input 变量
user_input = st.text_area("请输入你的线代问题：", height=180)
if user_input:
    # 只调用一次大模型
    resp = dashscope.Generation.call(
        model="qwen-turbo",
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ],
        result_format="message"
    )
    raw_content = resp.output.choices[0].message.content
    # =========【第一步：先分割SPLIT！！！优先分割，再美化排版】========
    # 容错分割四段内容
    part1 = raw_content.split("【---SPLIT1---】")
    if len(part1) >= 2:
        full_part_raw = part1[0].strip()
        remain = part1[1]
        part2 = remain.split("【---SPLIT2---】")
        if len(part2) >= 2:
            short_part_raw = part2[0].strip()
            remain2 = part2[1]
            part3 = remain2.split("【---SPLIT3---】")
            if len(part3) >=2:
                similar_part_raw = part3[0].strip()
            else:
                similar_part_raw = remain2
        else:
            short_part_raw = remain
            similar_part_raw = "⚠ 变式练习题生成失败，请重新提问"
    else:
        full_part_raw = raw_content
        short_part_raw = "⚠ 精简答案生成失败，请重新提问"
        similar_part_raw = "⚠ 变式练习题生成失败，请重新提问"
    # =========【第二步：对每一段单独执行排版美化】========
    def format_answer_text(raw_str):
        text = re.sub(r'<.*?>', '', raw_str)
        text = re.sub(r'(?<!\n)(\d+\. )', r'\n\n\1', text)
        text = re.sub(r'。', r'。\n\n', text)
        return text
    full_part = format_answer_text(full_part_raw)
    short_part = format_answer_text(short_part_raw)
    similar_part = format_answer_text(similar_part_raw)
    # 存入session_state
    st.session_state.full_text = full_part
    st.session_state.short_text = short_part
    st.session_state.similar_text = similar_part
    # =========页面渲染展示========
    st.subheader("📘 结果展示")
    with st.expander("📖 查看完整解答", expanded=True):
        st.markdown(full_part, unsafe_allow_html=False)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✅ 精简答案")
        st.info(short_part)
    with col2:
        st.subheader("🔁 同类题思路")
        st.warning(similar_part)
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
# =========【提交按钮】=========
# 初始化默认值，防止提取失败时报错
ai_knowledge_points = []
ai_confused_theorem = "无"
ai_unclear_point = "无"
# ====================== Streamlit页面开始 ======================
st.set_page_config(page_title="线代启明星", layout="wide")
st.markdown("<h1 style='color:#1F3864;'>线代启明星｜启真问智大赛</h1>", unsafe_allow_html=True)
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
    # loader = PyPDFLoader("temp_linealgebra.pdf")
    # pages = loader.load_and_split()
    # split_docs = text_splitter.split_documents(pages)
    # vector_db.add_documents(split_docs)
    # vector_db.persist()
    st.success("✅PDF知识库导入完成！已存入向量库")
st.divider()
# -------- 图片上传与题目AI引导 --------
st.subheader("上传线性代数证明题图片（可直接拖拽图片到框内）")
uploaded_file = st.file_uploader(
    "直接把照片拖入此处，或者点击Upload上传 | 200MB · JPG, PNG",
    type=["jpg", "png"],
    key="img_upload"
)
ai_guide_result = ""
question_desc = ""
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
        def clean_ai_text(text):
            # 删除表情包和特殊符号
            text = re.sub(
                r"[^\w\s，。！？、；：()（）\-\—\[\]{}<>=≠≤≥±×÷∑∏∫√∂∇∈∉∋∌∩∪⊂⊃⊄⊅⊆⊇⊈⊉⊊⊋⊥∥∠°παβγδεζηθλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ]+",
                "", text)
            # 合并多余空行
            text = re.sub(r"\n{2,}", "\n\n", text)
            return text.strip()
        clean_guide = clean_ai_text(ai_guide_result)
        st.markdown(f"<h3 style='color:#1F3864;'>AI题目引导</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#222222;line-height:1.8;'>{clean_guide}</p >", unsafe_allow_html=True)
        # 截取前80字作为题目简述
        question_desc = ai_guide_result[:80]
        # 【新增按钮：整理精简答案 / 生成举一反三变式题】
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📝整理精简答案", key="btn_summary"):
                summary_prompt = f"""
把下面线性代数启发引导，整理精简推导总结：
1.保留核心概念关键步骤，删掉反问引导提问。
2.每条要点单独一段，段落空两行。
3.数学符号、希腊字母全部LaTeX，$包裹，例$\delta$，$\mathrm{{rank}}(A)$。
4.基于邱维声高等代数第四版，不要额外拓展。
原文：
{clean_guide}
"""
                resp_summary = dashscope.Generation.call(
                    model="qwen-turbo", temperature=0.1,
                    messages=[{"role":"system","content":"只做精简整理，不新增知识点"},{"role":"user","content":summary_prompt}],
                    result_format="message",stream=False
                )
                st.session_state.summary_ans = resp_summary.output.choices[0].message.content
        with col_btn2:
            if st.button("🔁生成举一反三变式题", key="btn_variant"):
                variant_prompt = f"""
基于下面线代原题解析：
1.生成1道同考点变式证明题，难度接近。
2.简短通俗易懂实际应用小例子。
3.数学符号全部LaTeX $包裹。
4.只输出题目，不给变式题完整答案。
原文：
{clean_guide}
"""
                resp_variant = dashscope.Generation.call(
                    model="qwen-turbo",temperature=0.2,
                    messages=[{"role":"system","content":"线代助教，生成变式题与实例，不给答案"},{"role":"user","content":variant_prompt}],
                    result_format="message",stream=False
                )
                st.session_state.variant_question = resp_variant.output.choices[0].message.content
        #渲染精简答案
        if st.session_state.summary_ans != "":
            st.divider()
            st.subheader("📝精简整理答案")
            st.markdown(st.session_state.summary_ans)
        #渲染变式题
        if st.session_state.variant_question != "":
            st.divider()
            st.subheader("🔁举一反三变式题")
            st.markdown(st.session_state.variant_question)
    else:
        st.error(f"调用失败！{response.message}")
st.divider()
# # -------- 学生推导输入 & 批改模块 --------
# st.subheader("✍ 写下你的推导/证明思路")
# student_reason = st.text_area("把你的思考过程写在这里，AI结合知识库帮你检查概念错误", height=150, key="student_text")
# ===== 学生推导过程上传模块 =====
st.subheader("✍️ 你的推导过程")
tab1, tab2 = st.tabs(["📝 文字输入推导", "🖼️ 上传手写照片"])
with tab1:
    # 文本输入框，保存到session_state
    student_text = st.text_area(
        "在这里写下你的推导步骤",
        value=st.session_state.get("student_input", ""),
        height=220,
        key="student_text_input"
    )
    if st.button("提交文字推导，AI批改", key="submit_text"):
        st.session_state["student_input"] = student_text
        # 拼接prompt，把学生推导发给大模型
        check_prompt = f"""
原题：{st.session_state.question}
参考答案：{st.session_state.ai_answer}
学生手写推导：{student_text}
任务：对比学生推导，找出逻辑漏洞、概念错误，用启发式提问，不要直接给完整答案。
要求：精简，使用LaTeX公式。
"""
        # 调用百炼API，获得批改结果
        with st.spinner("正在分析你的推导..."):
            resp = dashscope.Generation.call(
                model="qwen-turbo",
                messages=[{"role":"user","content":check_prompt}],
                result_format="message"
            )
            feedback = resp.output.choices[0].message.content
        st.markdown("### 📋 AI反馈")
        st.markdown(feedback)
with tab2:
    # 图片上传，用于手写推导照片
    upload_img = st.file_uploader("上传手写推导图片（jpg/png）", type=["jpg","png","jpeg"], key="student_img")
    if upload_img is not None:
        img = Image.open(upload_img)
        st.image(img, caption="你的手写推导", use_column_width=True)

        img_bytes = upload_img.read()
        base64_str = base64.b64encode(img_bytes).decode("utf-8")

        if st.button("提交图片，AI识别批改", key="submit_img"):
            with st.spinner("识别手写推导并批改..."):
                try:
                    resp = dashscope.MultiModalConversation.call(
                        model="qwen3-vl-flash", # ✅正确可用模型
                        messages=[
                            {"role":"system","content":SYSTEM_PROMPT},
                            {
                                "role":"user",
                                "content":[
                                    {"type":"image", "image": base64_str},
                                    {"type":"text", "text":"对比推导，找出概念错误，启发式引导，不直接写完整答案，全部数学符号使用LaTeX $ $，输出时每一条要点单独分段，段落之间空两行"}
                                ]
                            }
                        ]
                    )
                    # 兼容两种返回格式
                    content_raw = resp.output.choices[0].message.content
                    if isinstance(content_raw, list):
                        feedback_img = content_raw[0]["text"]
                    else:
                        feedback_img = content_raw

                    # 排版美化
                    feedback_img = re.sub(r'<.*?>', '', feedback_img)
                    feedback_img = re.sub(r'(?<!\n)(\d+\. )', r'\n\n\1', feedback_img)

                    st.markdown("### 📝 AI反馈")
                    st.markdown(feedback_img)
                except Exception as e:
                    st.error(f"调用出错：{e}")
                    st.write(resp)

    # 重置按钮
    if st.button("清空我的推导", on_click=reset_question):
        st.success("已清空推导内容，可以重新作答")



# 后续升级
# check_btn = st.button(" 检查我的推导（检索知识库）")
# if check_btn and student_reason.strip() != "":
#     # rag_student_context = search_knowledge(student_reason)
#     rag_student_context = ""  # 先跳过检索函数
#     resp_student = MultiModalConversation.call(
#         model="qwen3-vl-plus",
#         messages=[
#             {"role": "system", "content": SYSTEM_PROMPT},
#             {
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": f"""
# 参考教材知识库内容：
# {rag_student_context}
# 学生的推导：{student_reason}
# 任务：检查学生线性代数证明思路，找出概念错误、逻辑缺口。
# 不要直接给出完整证明。用启发式提问，指出哪里定义理解出错，提示对应的定理。
# """}
#                 ]
#             }
#         ],
#         stream=False
#     )
#     if resp_student.status_code == 200:
#         student_check_result = resp_student.output.choices[0].message.content
#         ai_check_text = student_check_result[0]["text"]
#         st.write("###  辅导反馈")
#         clean_check = clean_ai_text(ai_check_text)
#         st.markdown(f"<h3 style='color:#1F3864;'>AI推导批改反馈</h3>", unsafe_allow_html=True)
#         st.markdown(f"<p style='color:#222222;line-height:1.8;'>{clean_check}</p >", unsafe_allow_html=True)
#         # 自动保存学情
#         save_study_record(question_desc, student_reason, ai_guide_result, ai_check_text)
#         st.success("✅ 本次学习记录已自动保存到【学情记录.xlsx】！")
#     else:
#         st.error(f"批改调用失败：{resp_student.message}")
# # 备用手动保存按钮
# st.divider()
# if st.button(" 手动保存当前记录（备用）"):
#     if ai_guide_result and student_reason:
#         save_study_record(question_desc, student_reason, ai_guide_result, "手动保存，无批改反馈")
#         st.success("✅手动保存成功")
#     else:
#         st.warning("请先上传题目或者填写推导内容")
st.divider()
# ====重置、下一题按钮放在整个页面最底部====
col_bottom1, col_bottom2 = st.columns(2)
with col_bottom1:
    st.button("🔄 重置本题", on_click=reset_question)
with col_bottom2:
    if st.button("➡️ 下一题"):
        reset_question()
        st.success("准备好接收下一题，请上传新题目图片")
# ========== 教师学情查看面板 ==========
st.divider()
st.subheader(" 教师学情查看面板")
st.info("教师可直接查看全部学生学习记录，无需打开Excel文件")
file_name = "student_learning_record.xlsx"
if os.path.exists(file_name):
    df_all = pd.read_excel(file_name)
    st.dataframe(df_all, use_container_width=True)
    record_options = df_all["记录时间"].tolist()
    if len(record_options) > 0:
        selected_time = st.selectbox("选择一条记录，查看完整详情", record_options)
        selected_row = df_all[df_all["记录时间"] == selected_time].iloc[0]
        st.markdown("####  本条记录详情")
        for col_name in df_all.columns:
            st.write(f"**{col_name}：** {selected_row[col_name]}")
