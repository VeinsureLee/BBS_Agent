import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 向量数据库路径
VECTOR_DB_PATH = os.path.join(BASE_DIR, "chroma_db")

# 数据文件路径
DATA_PATH = r""

# Neo4j配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = " "#neo4j端密码

# LLM配置（可切换 DeepSeek）
OPENAI_API_KEY = "XXX"
OPENAI_BASE_URL = "https://api.longcat.chat/openai"
OPENAI_MODEL = "LongCat-Flash-Lite"

#DeepSeek
# OPENAI_BASE_URL = "https://api.deepseek.com"
# OPENAI_MODEL = "deepseek-chat"
# OPENAI_API_KEY = "XXX"

#向量嵌入模型
EMBEDDING_MODEL = "BAAI/bge-base-zh"

TOP_K_GRAPH = 5
TOP_K_VECTOR = 5
