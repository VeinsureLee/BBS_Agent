import re
from neo4j import GraphDatabase
import config


class Neo4jService:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )

    def extract_entities(self, question):

        words = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]+", question)

        stopwords = ["什么", "多少", "哪些", "情况", "如何"]

        entities = [w for w in words if w not in stopwords]

        return entities

    # 查询函数
    def search(self, question):

        entities = self.extract_entities(question)

        all_results = []

        for e in entities:

            cypher = """
MATCH (n)
WHERE n.name = $name
OPTIONAL MATCH p1 = (n)-[*1..2]-(m)
OPTIONAL MATCH p2 = (x)-[*1..2]-(n)
RETURN n, p1, p2
"""

            with self.driver.session() as session:
                result = session.run(cypher, name=e)

                for record in result:
                    paths = []
                    if record["p1"]:
                        paths.append(record["p1"])
                    if record["p2"]:
                        paths.append(record["p2"])

                    for rel in paths.relationships:
                        a = rel.start_node["name"]
                        b = rel.end_node["name"]
                        r = rel.type

                        triple = f"{a} -[{r}]-> {b}"
                        all_results.append(triple)

        if not all_results:
            return "无图谱信息"

        return "\n".join(list(set(all_results)))
    
    def get_global_key_nodes(self):

        cypher = """
    MATCH (n)
    OPTIONAL MATCH (n)<-[r_in]-()
    OPTIONAL MATCH (n)-[r_out]->()
    WITH n, count(r_in) + count(r_out) AS total_degree
    ORDER BY total_degree DESC
    LIMIT 20
    RETURN n.name AS name, total_degree
    """

        with self.driver.session() as session:
            result = session.run(cypher)

            nodes = [record["name"] for record in result]

        return nodes