import os,time
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

from mystyle import add_my_styles, para_fm, run_fm
from float_picture import parse_xml, nsdecls, add_float_picture
from load_config import load_user_config


def apply_font_scaling(run, scaling):
    """对 run 内的所有文字应用字体横向缩放

    :param run: python-docx 的 Run 对象
    :param scaling: 缩放比例
    """
    try:
        if not run.text:
            return
        rPr = run._r.get_or_add_rPr()
        # 先一次性移除所有旧的 w:w 元素，避免循环中反复 append
        for existing in rPr.findall(qn('w:w')):
            rPr.remove(existing)
        # 再添加新的 w:w，namespace 由 parse_xml 自动处理，无需手动写 xmlns
        w_elem = parse_xml('<w:w {} w:val="%d"/>'.format(nsdecls('w')) % scaling)
        rPr.append(w_elem)
    except Exception as e:
        print(f'字体缩放失败: {e}')


def add_seal(workdir):
    # 获取脚本所在目录（用于读取config）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 先检查是否有可处理的文件
    files_to_process = [f for f in os.listdir(workdir) if f.lower().endswith('.docx') and f[:4].isdigit()]
    if not files_to_process:
        print('没有可处理的文件，请先添加页码')
        return
    
    #3署名及日期设置
    for file in files_to_process:
        print('正在添加印章：',file)
        file_path = os.path.join(workdir, file)
        doc=Document(file_path)
        add_my_styles(doc)
        paras=doc.paragraphs
        sign_para_text='未找到署名'
        for para in paras:
            para_text=''.join(para.text.split())
            if '年' in para_text and '月' in para_text\
                and '日' in para_text and len(para_text) < 12:
                sign_para = paras[paras.index(para)-1]   #日期上一段
                sign_text = ''.join(sign_para.text.split())
                if len(sign_text)>3 and len(sign_text) < 25:
                    print('第{}段有署名：{}'.format(paras.index(para), sign_text))
                    sign_para_text = sign_text
                try:
                    picture_name = get_stamp_path(sign_para_text)
                    if picture_name:
                        n=len(para_text)
                        if n == 9:
                            x0=(21-2.6)*28.35-64-7*16/2       #x0是日期的中心坐标
                        elif n ==10:
                            x0=(21-2.6)*28.35-64-7.5*16/2
                        elif n ==11:
                            x0=(21-2.6)*28.35-64-8*16/2
                        else:
                            pass
                        y0 = 28.95*10.5+3.7*28.35
                        x1 = x0-5.7/2*28.35 ; y1 = y0-5.24/2*28.35   #x0是图片中心坐标
                        add_float_picture(para, picture_name , pos_x=Pt(x1), pos_y=Pt(y1-40))  ## 测试插入浮动图片2022.1.9
                        print('印章添加成功。')
                    else:
                        print('未找到印章配置。')
                except Exception as e:
                    print(f'印章添加失败：{e}')
                break
                
        #套红并缩放
        para = paras[0].insert_paragraph_before()   #最前段插入发文机关
        para.style = doc.styles['H0']
        para_fm(para,0,0,1,0,0,0,'C')
        run0 = para.add_run(sign_para_text+'文件')
        run_fm(run0,'方正小标宋简体',72,0,255,0,0)
        apply_font_scaling(run0, int(560/(len(sign_para_text)+2)))
        
        para = paras[0].insert_paragraph_before()   #插入空行
        para.style = doc.styles['Fangsong']
        para_fm(para,0,0,28.95,0,0,0,'C')
        run_fm(para.add_run(''),'仿宋', 16,0,0,0,0)

        #插入文号及分割线
        para = paras[0].insert_paragraph_before()
        para.style = doc.styles['Fangsong']
        para_fm(para,0,0,28.95,0,0,0,'C')
        wenhao = get_fawenzihao(sign_para_text)
        run_fm(para.add_run(wenhao),'仿宋', 16,0,0,0,0)
        pPr = para._p.get_or_add_pPr()
        # 底边框：红色 FF0000、单实线、粗细 12（=1.5pt）、间距 3
        pPr.insert(1, parse_xml(
            '<w:pBdr {}>'.format(nsdecls('w')) +
            '<w:bottom w:val="single" w:sz="12" w:space="3" w:color="FF0000"/>' +
            '</w:pBdr>'
        ))
        print('文号：',wenhao)

        para = paras[0].insert_paragraph_before()   #插入空行
        para_fm(para,0,0,28.95,0,0,0,'C')
        run_fm(para.add_run(''),'仿宋', 16,0,0,0,0)

        #文档保存docx
        file = str(wenhao)+file[4:]
        save_path = os.path.join(workdir, file)
        doc.save(save_path)
        print('文档已保存：', os.path.normpath(save_path), '\n')

    
def get_stamp_path(sign_text):
    """获取印章图片路径"""
    config = load_user_config()
    if not config:
        return None
    
    # 获取项目根目录（脚本所在目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 遍历配置，查找匹配的公司名称或简称
    for company, info in config.items():
        if not isinstance(info, dict):
            continue  # 跳过非公司配置（compare、last_workdir 等）
        if company == sign_text or sign_text in info.get('简称', []):
            # 优先使用配置中的印章位置
            stamp_path = info.get('印章位置')
            if stamp_path:
                # 如果是相对路径，基于项目根目录
                if not os.path.isabs(stamp_path):
                    stamp_path = os.path.join(script_dir, stamp_path)
                return stamp_path
            # 如果没有配置印章位置，使用默认方式
            return os.path.join(script_dir, 'config', sign_text + '.png')
    
    return None


def get_fawenzihao(sign_text):
    """获取发文字号"""
    config = load_user_config()
    daizi = '未找到'
    if config:
        for company, info in config.items():
            if not isinstance(info, dict):
                continue  # 跳过非公司配置
            if company == sign_text or sign_text in info.get('简称', []):
                daizi = info.get('代字')
                break  
    year = time.strftime("%Y", time.localtime())
    wenhao = daizi + '〔' + year + '〕' + '1号'
    return wenhao


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    add_seal(workdir)
