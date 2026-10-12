with tab2:
    st.subheader("📷 上传手写推导，AI直接识别图片批改")
    upload_img = st.file_uploader("上传手写推导图片（jpg/png，小于7MB）", type=["jpg","png","jpeg"], key="student_img")
    if upload_img is not None:
        # 读取图片二进制
        img_bytes_raw = upload_img.getvalue()
        if not img_bytes_raw:
            st.warning("图片读取失败，图片数据为空，请重新上传！")
        else:
            img = Image.open(upload_img)
            img = img.convert("RGB")
            max_width = 1200
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((int(img.width*ratio), int(img.height*ratio)))

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            compressed_bytes = buffer.getvalue()
            buffer.close()
            base64_str = base64.b64encode(compressed_bytes).decode("utf-8")

            st.image(img, caption="预览你的手写推导", use_column_width=True)

            if st.button("提交图片，AI启发式批改", key="submit_img_btn"):
                with st.spinner("正在识别手写推导并分析..."):
                    try:
                        # 【重点：使用MultiModalConversation，不要OpenAI兼容client！】
                        messages_student = [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image", "image": f"data:image/jpeg;base64,{base64_str}"},
                                    {
                                        "type": "text",
                                        "text": "识别图片内的线性代数手写推导。找出概念错误，启发式引导，严禁直接给出完整证明。数学公式使用$ $包裹LaTeX。输出每一条要点单独分段，要点之间空两行。"
                                    }
                                ]
                            }
                        ]

                        resp_img = MultiModalConversation.call(
                            model="qwen3-vl-plus",
                            messages=messages_student,
                            stream=False
                        )

                        if resp_img.status_code == 200:
                            feedback_img = resp_img.output.choices[0].message.content[0]["text"]
                            # 简单清理文本
                            feedback_img = re.sub(r'<.*?>', '', feedback_img)
                            feedback_img = re.sub(r'(?<!\n)(\d+\. )', r'\n\n\1', feedback_img)
                            st.markdown("### 📝 AI反馈")
                            st.markdown(feedback_img)
                        else:
                            st.error(f"接口返回错误：code={resp_img.status_code}, msg={resp_img.message}")

                    except Exception as e:
                        st.error(f"调用出错：{e}")
    # 重置按钮
    if st.button("清空我的推导", on_click=reset_question):
        st.success("已清空")
