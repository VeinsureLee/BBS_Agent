from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import Chroma
import config
import os


class VectorDB:

    def __init__(self):

        self.embeddings = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL
        )

        self.persist_dir = "chroma_db"

        #判断是否已存在数据库
        if os.path.exists(self.persist_dir):
            self.db = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=self.embeddings
            )
        else:
            self.db = self.build_db()

    #构建数据库
    def build_db(self):

        texts = self.load_text()

        db = Chroma.from_texts(
            texts=texts,
            embedding=self.embeddings,
            persist_directory=self.persist_dir
        )

        db.persist()
        return db

    #结构化切分
    def load_text(self):

        path = config.DATA_PATH

        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        blocks = raw_text.split("--------------------------------------------------")

        processed = []

        for block in blocks:

            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")

            publisher = "未知"
            content = ""
            actions = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if "发布内容" in line:
                    import re
                    m = re.match(r"用户(.*?)发布内容：", line)
                    if m:
                        publisher = m.group(1)

                    content = line.split("：", 1)[-1]

                elif "评论" in line or "转发" in line or "回复" in line:
                    actions.append(line)

            chunk = f"""
用户{publisher}发布了一个帖子：{content}。
该帖子被以下用户传播：{'；'.join(actions)}。
"""

            processed.append(chunk.strip())

        return processed

    # ⭐ 检索
    def search(self, query, top_k=3):

        docs = self.db.similarity_search(query, k=top_k)

        return "\n".join([d.page_content for d in docs])