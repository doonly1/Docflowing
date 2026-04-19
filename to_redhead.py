import os,time
from docx import Document
from docx.shared import Pt

from mystyle import para_fm,run_fm
from float_picture import parse_xml, nsdecls, CT_Anchor, add_float_picture


def add_seal(workdir):
    # 获取脚本所在目录（用于读取config）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 先检查是否有可处理的文件
    files_to_process = [f for f in os.listdir(workdir) if f.endswith('.docx') and f[:4].isdigit()]
    if not files_to_process:
        print('没有可处理的文件，请先添加页码')
        return
    
    #3署名及日期设置
    for file in files_to_process:
        print('正在添加印章：',file)
        file_path = os.path.join(workdir, file)
        doc=Document(file_path)
        paras=doc.paragraphs
        sign_para_text='未找到署名'
        for para in paras:
            para_text=para.text.replace(' ','')
            if '年' in para_text and '月' in para_text\
                and '日' in para_text and len(para_text)<12:
                sign_para = paras[paras.index(para)-1]   #日期上一段
                if len(sign_para.text)>3 and len(sign_para.text)<20:
                    print('第{}段有署名：{}'.format(paras.index(para),sign_para.text))
                    sign_para_text=sign_para.text.replace(' ','')
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
                
        #套红机关名
        para = paras[0].insert_paragraph_before()   #最前段插入发文机关
        para._p.get_or_add_pPr().insert(0,parse_xml('<w:snapToGrid {}  w:val="0"/>'.format(nsdecls('w')))) #取消设置对齐到网格
        run=para.add_run()
        run = para.add_run(sign_para_text+'文件')
        run_fm(run,'方正小标宋简体',72,255,0,0)
        para_fm(para,0,0,1,0,0,0,'C')
        
        para = paras[0].insert_paragraph_before()   #插入空行
        para._p.get_or_add_pPr().insert(0,parse_xml('<w:snapToGrid {}  w:val="0"/>'.format(nsdecls('w')))) #取消设置对齐到网格
        para_fm(para,0,0,28.95,0,0,0,'C')
        
        #插入文号
        para = paras[0].insert_paragraph_before()
        para._p.get_or_add_pPr().insert(0,parse_xml('<w:snapToGrid {}  w:val="0"/>'.format(nsdecls('w')))) #取消设置对齐到网格
        run = para.add_run()
        fawenzihao = get_fawenzihao(sign_para_text)
        run.text = fawenzihao
        run_fm(run,'仿宋')
        para_fm(para,0,0,28.95,0,0,0,'C')
        print('文号已生成：',run.text)
        
        #插入红色分割线
        para = paras[0].insert_paragraph_before()
        para._p.get_or_add_pPr().insert(0,parse_xml('<w:snapToGrid {}  w:val="0"/>'.format(nsdecls('w')))) #取消设置对齐到网格
        para_fm(para,0,0,28.95,0,0,0,'C')
        
        line_name = os.path.join(script_dir, 'config', '红色分割线.png')
        run_fm(run,'仿宋',16)
        add_float_picture(para, line_name , pos_x=Pt(2.8*28.35), pos_y=Pt(10*28.35))
        


        #文档保存docx
        file = str(fawenzihao)+file[4:]
        save_path = os.path.join(workdir, file)
        doc.save(save_path)


        #应用重新打开，调整字体缩放
        ssss = 560/(len(sign_para_text)+2)
        import win32com.client as win32
        try:
            word = win32.gencache.EnsureDispatch('Word.Application')
        except Exception:
            word = win32.Dispatch('Word.Application') 
        word.Visible = 0
        file_path = os.path.normpath(os.path.join(workdir, file))
        doc = word.Documents.Open(file_path)    #打开新的文档
        doc.Paragraphs(1).Range.Font.Scaling = ssss
        doc.Save()
        doc.Close()
        print('文档已保存：', file_path, '\n')

    
def get_stamp_path(sign_text):
    """获取印章图片路径"""
    config = _load_config()
    if not config:
        return None
    
    # 获取项目根目录（脚本所在目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 遍历配置，查找匹配的公司名称或简称
    for company, info in config.items():
        if company == 'compare':
            continue  # 跳过比较配置
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
    config = _load_config()
    
    daizi = None
    # 遍历配置，查找匹配的公司名称或简称
    if config:
        for company, info in config.items():
            if company == 'compare':
                continue  # 跳过比较配置
            if company == sign_text or sign_text in info.get('简称', []):
                daizi = info.get('代字')
                break
    
    if daizi is None:
        daizi = '未找到'
        
    year = time.strftime("%Y", time.localtime())
    fawenzihao = daizi + '〔' + year + '〕' + '1号'
    return fawenzihao


def _load_config():
    """加载配置文件（用户自定义或默认）"""
    import yaml
    import os
    
    # 优先使用用户自定义配置
    user_config_path = os.environ.get('USER_CONFIG_PATH')
    if user_config_path and os.path.exists(user_config_path):
        config_path = user_config_path
    else:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.yaml')
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"警告：读取配置文件失败: {e}")
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    add_seal(workdir)
