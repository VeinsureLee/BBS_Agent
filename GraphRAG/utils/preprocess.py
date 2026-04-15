import re

def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"@\S+", "", text)
    text = re.sub(r"#", "", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()

# ⭐读取txt文件
def load_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    texts = []
    for line in lines:
        line = clean_text(line)
        if len(line) > 5:   # 过滤无效短文本
            texts.append(line)

    return texts