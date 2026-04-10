from docx import Document
from wordcloud import WordCloud
import os,jieba

from doc_process import doc_to_docx


def show_wordcloud(workdir):
    try:
        doc_to_docx(workdir)
    except Exception as e:
        print(f"  docx转换失败: {e}")

    for file in os.listdir(workdir):
        if file.endswith('.docx') and not file.startswith("~$"):
            file_path = os.path.join(workdir, file)
            print('正在生成词云：', file)
            doc = Document(file_path)
            paras_texts = ''
            for para in doc.paragraphs:
                paras_texts += para.text
            words = ' '.join(jieba.lcut(paras_texts))
            font = r'C:\Windows\Fonts\simfang.ttf'
            wordcloud = WordCloud(collocations=False, font_path=font, stopwords={"的","和"},
                                  width=1980, height=1080, margin=2).generate(words)
            png_path = os.path.join(workdir, os.path.splitext(file)[0] + '.png')
            wordcloud.to_file(png_path)
            print('词云成功：', png_path)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    show_wordcloud(workdir)
