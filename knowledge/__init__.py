"""
knowledge 包：BBS 知识库的爬取、存储、检索与处理。

功能说明：
    - ingestion：讨论区列表与版面树爬取、置顶帖与帖子详情解析与介绍 JSON 归档、按讨论区/版面增量更新动态帖；
                  命令行入口 python -m knowledge.ingestion。详见 knowledge.ingestion.__init__。
    - stores：三套向量库封装（Chroma）——动态帖（data/dynamic）、结构（data/static）、用户上传；
              含初始化、MD5 去重、config/init.json 状态更新。详见 knowledge.stores.__init__。
    - retrieval：对上述三套库的检索封装——动态帖相似度检索、结构库按版面信息/多维度检索、用户库相似度检索；
                 详见 knowledge.retrieval.__init__。
    - processing：帖子楼层 content 分块清理（clean）、版面标签生成（tagger，大模型生成 JSON 写入 data/static）；
                 详见 knowledge.processing.__init__。

入参/出参：各子包 __init__.py 与各模块文件头均有说明，可直接 from knowledge.ingestion import ... 等按需引用。
"""

