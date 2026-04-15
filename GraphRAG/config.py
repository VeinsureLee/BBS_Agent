import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 向量数据库路径
VECTOR_DB_PATH = os.path.join(BASE_DIR, "chroma_db")

# 数据文件路径
DATA_PATH = r"D:/11personal information/毕设/code/weibo_data.txt"

# Neo4j配置
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "lyz_neo4j"

# LLM配置（可切换 DeepSeek）
OPENAI_API_KEY = "ak_2EG0aE6SW6fM1xp1rL2vV6WP2Fg43"
OPENAI_BASE_URL = "https://api.longcat.chat/openai"
OPENAI_MODEL = "LongCat-Flash-Lite"

#DeepSeek
# OPENAI_BASE_URL = "https://api.deepseek.com"
# OPENAI_MODEL = "deepseek-chat"
# OPENAI_API_KEY = "sk-eb1805b91b034f3bb56411eee66b7eb1"

#向量嵌入模型
EMBEDDING_MODEL = "BAAI/bge-base-zh"

TOP_K_GRAPH = 5
TOP_K_VECTOR = 5