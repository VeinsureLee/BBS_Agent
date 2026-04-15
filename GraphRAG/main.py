from core.retriever import Retriever
from core.generator import Generator
from graph.neo4j_service import Neo4jService

class GraphRAGQA:

    def __init__(self):
        self.retriever = Retriever()
        self.generator = Generator()
        self.graph = Neo4jService()

    def route_query(self, question):

        analysis_keywords = [
            "关键节点", "传播节点", "重要节点",
            "影响力", "核心节点", "谁最重要",
            "排行榜", "top", "全图", "图中谁"
        ]

        if any(k in question for k in analysis_keywords):
            return "analysis"

        return "qa"

    def ask(self, question):

        mode = self.route_query(question)

        #图分析问题（关键节点 / 传播分析）
        if mode == "analysis":

            key_nodes = self.retriever.global_retrieve()

            return self.generator.global_generate(question, key_nodes)

        #普通问答（GraphRAG）
        else:

            context = self.retriever.local_retrieve(question)

            return self.generator.local_generate(question, context)


if __name__ == "__main__":

    system = GraphRAGQA()

    while True:
        q = input("\nUser: ")
        print("\nAssistant:", system.ask(q))