import re
from graph.neo4j_service import Neo4jService
from rag.vector_db import VectorDB


class Retriever:

    def __init__(self):
        self.graph = Neo4jService()
        self.vector = VectorDB()

    #query理解
    def extract_keywords(self, query):

        keywords = []

        # 用户名
        user_match = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]+", query)
        keywords.extend(user_match)

        # 特定关键词
        for k in ["龙虾", "OpenClaw"]:
            if k in query:
                keywords.append(k)

        return list(set(keywords))

    #子图检索
    def local_retrieve(self, query):

        keywords = self.extract_keywords(query)

        #用关键词去查图
        graph_results = []
        for k in keywords:
            res = self.graph.search(k)
            if "无图谱匹配" not in res:
                graph_results.append(res)

        graph_info = "\n".join(graph_results) if graph_results else "无图谱信息"

        #vector查询
        vector_info = self.vector.search(query)

        return {
            "graph": graph_info,
            "vector": vector_info
        }
    
    #全局检索
    def global_retrieve(self):
        return self.graph.get_global_key_nodes()