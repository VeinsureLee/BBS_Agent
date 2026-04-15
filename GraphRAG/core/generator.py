from openai import OpenAI
from config import OPENAI_API_KEY,OPENAI_BASE_URL,OPENAI_MODEL

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

from openai import OpenAI
from config import OPENAI_API_KEY,OPENAI_BASE_URL,OPENAI_MODEL

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

class Generator:

    def local_generate(self, question, context):

        prompt = f"""
你是舆情传播路径问答系统。

基于以下信息回答用户问题：

【知识图谱传播路径】
{context['graph']}

【语义补充信息】
{context['vector']}
"""

        prompt += f"""

【用户问题】
{question}

要求：
- 用自然语言回答
- 不要输出报告结构
"""

        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "GraphRAG QA system"},
                {"role": "user", "content": prompt}
            ]
        )

        return resp.choices[0].message.content
    
    def global_generate(self, question, key_nodes):

        return "当前图中的关键传播节点包括：\n" + "、".join(key_nodes)