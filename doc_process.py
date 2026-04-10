from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import time
import os

from mystyle import para_fm, run_fm, clear_styles, add_my_styles, my_number_style, set_page
from win32com import client
from win32com.client import constants


def doc_to_docx(workdir):
    """将workdir目录下的.doc文件批量转换为.docx格式"""
    word = client.Dispatch("Word.Application")
    word.Visible = False
    for file in os.listdir(workdir):
        if file.endswith('.doc') and not file.startswith("~$"):
            print('转化docx：{}'.format(file))
            file_path = os.path.join(workdir, file)
            doc = word.Documents.Open(file_path) 
            doc.SaveAs("{}x".format(file_path), 12)  # 12 = docx格式
            doc.Close()
            try:
                os.remove(file_path)
            except:
                pass
    word.Quit()

def save_docx(doc, doc_name, workdir=None):
    """
    保存Word文档
    
    Args:
        doc: Document对象
        doc_name: 文件名（可包含路径）
        workdir: 可选的保存目录，默认为None（当前目录）
    
    Returns:
        保存的完整文件路径，失败返回None
    """
    import re
    import zlib
    
    # 分离目录和文件名
    if workdir is None:
        # 如果doc_name包含路径，分离出来
        if os.path.dirname(doc_name):
            workdir = os.path.dirname(doc_name)
            doc_name = os.path.basename(doc_name)
        else:
            workdir = os.getcwd()
    
    # 清理文件名中的非法字符
    doc_name = re.sub(r'[\\/:*?"<>|]', '_', doc_name)
    
    # 确保扩展名正确
    if not doc_name.endswith('.docx'):
        doc_name += '.docx'
    
    # 生成目标文件名哈希前缀（4位纯数字）
    hash_prefix = str(zlib.crc32(doc_name.encode()) % 10000).zfill(4)
    
    # 检查目标文件是否已存在（已另存过）
    save_path = os.path.normpath(os.path.join(workdir, hash_prefix + "_" + doc_name))
    if os.path.exists(save_path):
        return save_path
    
    try:
        doc.save(save_path)
        print(f"已另存: {save_path}")
        return save_path
    except Exception as e:
        print(f"另存失败: {e}")
        return None

def set_headings(doc):
    paras=doc.paragraphs
    title = ['决议','决定','命令','公报','公告','通告','意见',\
                '通知','通报','报告','请示','批复','议案','的函','纪要',\
                '计划','总结','申请','名单','制度','办法','规定','方案','要点']
    heading1=['一、','二、','三、','四、','五、','六、',\
              '七、','八、','九、','十、']
    heading2=['（一）','（二）','（三）','（四）','（五）',\
              '（六）','（七）','（八）','（九）','（十）']
    for para in paras:                          
        if paras.index(para)<3 and len(para.text)<60 and para.text.strip(" ")[-2:] in title:  #标题识别
            para.style = doc.styles['Tit']
            para_fm(para,0,0,28.95,0,0,0,'C')
            for run in para.runs:
                run_fm(run,'方正小标宋简体',22,0,0,0)

        if 1<len(para.text)<30 and '：' in para.text[-1] \
           and len(paras[paras.index(para)-1].text)==0:  #主送识别
            para.style = doc.styles['unindent']
            para_fm(para,0,0,28.95,0,0,0,'J')
            for run in para.runs:
                run_fm(run,'仿宋',16,0,0,0)

        if para.text.strip(" ")[:2] in heading1 and len(para.text)<60 and '：' not in para.text:  #一级标题识别
            para.style = doc.styles['H1']
            for run in para.runs:
                run_fm(run,'黑体',16,0,0,0)

        if para.text.strip(" ")[:3] in heading2 and len(para.text)<60 and '：' not in para.text:   #二级标题识别
            para.style = doc.styles['H2']
            for run in para.runs:
                run_fm(run,'楷体',16,0,0,0)
        
def set_appendix(doc):
    paras=doc.paragraphs
    #2段落遍历完毕后，再次遍历到“附件”段落。设置附件格式，并获得其个数和内容。
    dx_s=[]      #进入循环前，确定卡点变量不被重复覆盖。
    for para in paras:
        dx='附件：'
        if dx in para.text[:5] and len(para.text)>3:
            dx_s.append(paras.index(para))	 #附件段落序列数

    n = 0  # 初始化n
    if len(dx_s) !=0:   #如果有附件
        dx_n_strs=[]
        for n in range(len(paras[dx_s[0]+1:])):		#往后每一段，遍历查找附件
            if str(n+1)+'.' in paras[dx_s[0]+n].text[:6]:  #判断n.在不在前6个字符内
                dx_n_str=paras[dx_s[0]+n].text[2:] #获得单个附件字符串
                for p in ['：','.','。']:	  #去掉标点
                    if p in dx_n_str:
                        dx_n_str=dx_n_str.replace(p,'')
                dx_n_strs.append(dx_n_str)	#获得所有附件的字符串

        if len(dx_n_strs)==0:
            dx_n_strs.append(paras[dx_s[0]].text[3:]) #只有一个附件时
            paras[dx_s[0]].style=doc.styles['Apdix']
            para_fm(paras[dx_s[0]],0,0,28.95,80,0,-48,'L')   #段落格式
			
        n=len(dx_n_strs)  #有n个附件
#        print('有{}个附件'.format(n))
    
    if len(dx_s) != 0 and n>0:    #如果有附件
        for i in range(n):
            for j in range(n):		  #遍历所有附件
                if str(i+1)+'.' in paras[dx_s[0]+j].text:
                    paras[dx_s[0]+j].style=doc.styles['Apdix 2']
                    para_f=paras[dx_s[0]+j].paragraph_format   #段落格式赋给para_f
                    para_f.alignment=WD_PARAGRAPH_ALIGNMENT.LEFT  #对齐方式
                    para_f.first_line_indent = Pt(0) 
                    para_f.left_indent = Pt(16*6)   #左缩进（Inches,Cm，Pt）需弥补悬挂负值
                    para_f.first_line_indent = Pt(-16)  #悬挂1个字符
        paras[dx_s[0]].style=doc.styles['Apdix 1']     #重设附件1.的格式
        para_fm(paras[dx_s[0]],0,0,28.95,16*6,0,0,'L')
        para_fm(paras[dx_s[0]],0,0,28.95,16*6,0,-16*4,'L')  #重设附件1.的格式

    #4查找|附件|，标记到[]
    ps=[]
    if len(dx_s) != 0:
        for para in paras[dx_s[0]:len(paras)-1]:
            
            if '附' in para.text and '件' in para.text and len(para.text)<5:   #找到顶格'附件'
                ps.append(paras.index(para))
#                print('第{}段有|附件|：{}'.format(ps[-1]+1,para.text.strip('\n')))
                if '：' in para.text[-1]:
                    para.text=para.text[:-1]
                para.style=doc.styles['Blackbody']	#设置顶格附件样式
                para_fm(para,0,0,28.95,0,0,0,'L')
                for run in para.runs:
                    run_fm(run,'黑体',16,0,0,0)	#设置顶格附件格式

    #5取用[]于后续比对
    if len(ps) != 0:
        p=ps[0]
        for para in paras[p:]:   #其下的每一段与附件说明内逐个对比
            for _str in dx_n_strs:
                if len(para.text)>2 and similar(para.text,_str)==1:
#                    print('第{}段有附件标题：{}'.format(paras.index(para)+1,para.text))
                    para.style=doc.styles['Tit']
                    para_fm(para,0,0,28.95,0,0,0,'C')
                    for run in para.runs:
                        run_fm(run,'方正小标宋简体',22,0,0,0)
                                         
def similar(text_a,text_b):
    if type(text_a)==type([]):
        a=set(text_a)
        b=set(text_b)
    elif type(text_a)==type('你好'):
        a=set(list(text_a))
        b=set(list(text_b))
    ab = a & b
    ba = a ^ b
    if len(ab)/(0.1+len(ba))>2:
        return 1
    else:
        return 0

def set_date(doc):
    #3署名及日期设置 
    paras=doc.paragraphs
    for para in paras:
        if '年' in para.text and '月' in para.text\
           and '日' in para.text and len(para.text)<12:
            # print('第{}段有日期：{}'.format(paras.index(para)+1,para.text))
            para.style=doc.styles['dater']	#日期格式
            para_fm(para,0,0,28.95,0,16*4,0,'R')	#日期格式
            
            paras[paras.index(para)-1].style = doc.styles['Sign']   #日期上一段的样式
            para_fm_bef=paras[paras.index(para)-1].paragraph_format   #日期上一段的格式
            para_fm_bef.alignment=WD_PARAGRAPH_ALIGNMENT.RIGHT
            para_fm_bef.first_line_indent = Pt(0)
            b=len(paras[paras.index(para)-1].text)  # b是日期上方署名的字符数
            if len(para.text) in {9,10}:		  #判断日期的字符数
                para_fm_bef.right_indent = Pt((8-0.5*b)*16)
            elif len(para.text)==11:
                para_fm_bef.right_indent = Pt((8.5-0.5*b)*16)
