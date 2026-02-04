import os
from dotenv import load_dotenv

# 加载.env文件（默认读取项目根目录的.env）
# 如果.env文件在其他路径，可指定：load_dotenv("/path/to/your/.env")
load_dotenv()

# 现在可以像读取系统环境变量一样使用这些变量
BBS_Name = os.environ.get("BBS_Name")
BBS_Password = os.environ.get("BBS_Password")

# 打印结果
print(f"从.env加载的BBS_Name: {BBS_Name}")
print(f"从.env加载的BBS_Password: {BBS_Password}")
