# -*- coding: utf-8 -*-
"""
Word文档比较工具
比较 原-***.docx 和 终-***.docx 文档，生成比较结果文档
"""

import os
import glob
import difflib
import yaml
from docx import Document
from docx.shared import RGBColor, Pt
from docx.oxml.ns import qn  # noqa: F401

# 导入文档处理函数
from doc_process import (
    clear_styles, add_my_styles, my_number_style, 
    set_page, set_appendix, set_date, doc_to_docx
    )


def load_compare_config():
    """从yaml配置文件加载比较参数（支持用户自定义配置）"""
    config = _load_config()
    
    if config:
        compare_config = config.get('compare', {})
        sentence_threshold = compare_config.get('sentence_similarity_threshold', 0.40)
        para_threshold = compare_config.get('para_similarity_threshold', 0.40)
        return sentence_threshold, para_threshold
    
    return 0.40, 0.40  # 默认值


def _load_config():
    """加载配置文件（用户自定义或默认）"""
    import os
    
    # 优先使用用户自定义配置
    user_config_path = os.environ.get('USER_CONFIG_PATH')
    
    if user_config_path and os.path.exists(user_config_path):
        config_path = user_config_path
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config", "config.yaml")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"警告：读取配置失败: {e}")
        return None


def find_docx_files(workdir):
    """从目录中选择原版和终版文档
    
    Args:
        workdir: 工作目录
    
    Returns:
        (original, final) 文档路径元组
    """
    # 查找目录中的所有 docx 文件
    doc_to_docx(workdir)
    all_docs = glob.glob(os.path.join(workdir, "*.docx"))
    
    if len(all_docs) < 2:
        print(f"目录中只有 {len(all_docs)} 个 docx 文档，至少需要 2 个进行比较")
        return None, None
    
    # 目录中有 2 个及以上文档，让用户选择
    def select(prompt, choices):
        print(f"\n{prompt}:")
        for i, doc in enumerate(choices, 1):
            print(f"  {i}. {os.path.basename(doc)}")
        while True:
            try:
                choice = input(f"(回车默认1):").strip()
                idx = int(choice) if choice else 1
                if idx == 0:
                    return None
                if 1 <= idx <= len(choices):
                    return choices[idx - 1]
                print(f"请输入1-{len(choices)}")
            except ValueError:
                print("请输入数字")
    
    # 选择原稿
    original = select("选择原稿", all_docs)
    if not original:
        return None, None
    
    # 选择终稿
    final = select("选择终稿", all_docs)
    if not final:
        return None, None

    return original, final


def get_paragraphs_with_style(doc):
    """获取文档所有段落及样式信息"""
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text
        paragraphs.append({
            'text': text,
            'style': para.style.name if para.style else 'Normal'
        })
    return paragraphs


def char_level_diff(original_text, final_text):
    """
    字符级别差异比较
    返回: list of (标记, 字符)
    标记: 'equal', 'delete', 'insert'
    """
    # 使用SequenceMatcher进行字符级比较
    matcher = difflib.SequenceMatcher(None, original_text, final_text)
    
    result = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.append(('equal', original_text[i1:i2]))
        elif tag == 'delete':
            result.append(('delete', original_text[i1:i2]))
        elif tag == 'insert':
            result.append(('insert', final_text[j1:j2]))
        elif tag == 'replace':
            # 替换操作：新增在前，删除在后
            result.append(('insert', final_text[j1:j2]))
            result.append(('delete', original_text[i1:i2]))
    
    return result


def split_into_sentences(text):
    """按逗号和句号分割句子，保留标点符号"""
    import re
    # 按逗号和句号分割，保留标点符号
    sentences = re.split(r'([，。！？；：])', text)
    # 合并句子和标点符号
    result = []
    for i in range(0, len(sentences) - 1, 2):
        result.append(sentences[i] + sentences[i + 1])
    if len(sentences) % 2 == 1 and sentences[-1]:
        result.append(sentences[-1])
    return result


def sentence_level_diff(orig_text, final_text, result_para, SENTENCE_SIM_THRESHOLD):
    """
    句子级别差异比较
    无论整体相似度如何，都先按句子进行比对
    按句子相似度阈值进行字符级比对，低于阈值直接标记删除/新增
    """
    orig_sentences = split_into_sentences(orig_text)
    final_sentences = split_into_sentences(final_text)
    
    # 只有一个句子时，直接字符级比对
    if len(orig_sentences) == 1 and len(final_sentences) == 1:
        para_diff = char_level_diff(orig_text, final_text)
        for tag, text in para_diff:
            if tag == 'equal':
                result_para.add_run(text)
            elif tag == 'delete':
                run = result_para.add_run(text)
                run.font.color.rgb = RGBColor(0, 0, 255)
                run.font.strike = True
            elif tag == 'insert':
                run = result_para.add_run(text)
                run.font.color.rgb = RGBColor(255, 0, 0)
        return
    
    # 使用贪心匹配找最佳句子对应关系
    used_orig = set()
    used_final = set()
    
    # 记录句子级匹配关系
    sentence_match = []  # [(orig_idx, final_idx, ratio), ...]
    
    for f_idx, f_sent in enumerate(final_sentences):
        best_ratio = 0
        best_o_idx = -1
        for o_idx, o_sent in enumerate(orig_sentences):
            if o_idx in used_orig:
                continue
            ratio = difflib.SequenceMatcher(None, o_sent, f_sent).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_o_idx = o_idx
        
        if best_o_idx != -1:
            sentence_match.append((best_o_idx, f_idx, best_ratio))
            used_orig.add(best_o_idx)
            used_final.add(f_idx)
    
    # 按原始句子顺序输出
    for o_idx in range(len(orig_sentences)):
        if o_idx in used_orig:
            # 找对应的终句子
            matched = next((m for m in sentence_match if m[0] == o_idx), None)
            if matched is None:
                continue
            f_idx = matched[1]
            ratio = matched[2]
            f_sent = final_sentences[f_idx]
            o_sent = orig_sentences[o_idx]
            
            if ratio >= SENTENCE_SIM_THRESHOLD:
                # 句子相似度高，进行字符级比对
                para_diff = char_level_diff(o_sent, f_sent)
                for tag, text in para_diff:
                    if tag == 'equal':
                        result_para.add_run(text)
                    elif tag == 'delete':
                        run = result_para.add_run(text)
                        run.font.color.rgb = RGBColor(0, 0, 255)
                        run.font.strike = True
                    elif tag == 'insert':
                        run = result_para.add_run(text)
                        run.font.color.rgb = RGBColor(255, 0, 0)
            else:
                # 句子相似度低，直接标记新增+删除（红色在前，蓝色在后）
                run1 = result_para.add_run(f_sent)
                run1.font.color.rgb = RGBColor(255, 0, 0)
                run2 = result_para.add_run(o_sent)
                run2.font.color.rgb = RGBColor(0, 0, 255)
                run2.font.strike = True
        else:
            # 未匹配的原始句子（删除）
            run = result_para.add_run(orig_sentences[o_idx])
            run.font.color.rgb = RGBColor(0, 0, 255)
            run.font.strike = True
    
    # 输出未匹配的终句子（新增）
    for f_idx in range(len(final_sentences)):
        if f_idx not in used_final:
            run = result_para.add_run(final_sentences[f_idx])
            run.font.color.rgb = RGBColor(255, 0, 0)


def compare_with_python(original_path, final_path, output_path):
    """使用python-docx进行段落级对比，识别新增/删除/修改"""
    try:
        # 预加载配置，避免重复调用
        SENTENCE_SIM_THRESHOLD, PARA_SIM_THRESHOLD = load_compare_config()
        
        # 打开文档
        orig_doc = Document(original_path)
        final_doc = Document(final_path)
        
        # 获取段落
        orig_paras = get_paragraphs_with_style(orig_doc)
        final_paras = get_paragraphs_with_style(final_doc)
        
        # 创建比较结果文档
        result_doc = Document()
        clear_styles(result_doc)
        add_my_styles(result_doc)
        my_number_style(result_doc)
        set_page(result_doc)
        
        # 步骤1: 找出完全匹配的段落
        orig_matched = set()
        final_matched = set()
        
        orig_map = {}  # 文本 -> 索引列表
        final_map = {}
        
        for i, p in enumerate(orig_paras):
            if p['text'] not in orig_map:
                orig_map[p['text']] = []
            orig_map[p['text']].append(i)
            
        for i, p in enumerate(final_paras):
            if p['text'] not in final_map:
                final_map[p['text']] = []
            final_map[p['text']].append(i)
        
        # 匹配完全相同的段落
        for text, indices in final_map.items():
            if text in orig_map:
                for o_idx in orig_map[text]:
                    for f_idx in indices:
                        if o_idx not in orig_matched and f_idx not in final_matched:
                            orig_matched.add(o_idx)
                            final_matched.add(f_idx)
                            break
        
        # 步骤2: 找相似段落（可能是拆分或修改）
        
        final_unmatched = [i for i in range(len(final_paras)) if i not in final_matched]
        
        # 步骤3: 使用动态规划找最优匹配
        # f_match[f_idx] = o_idx (匹配的原始段落索引) 或 -1 (新增段落)
        f_match = [-1] * len(final_paras)
        
        # 标记已匹配的原文档段落
        matched_orig = set()
        
        # 1. 完全匹配优先
        for text, f_indices in final_map.items():
            if text in orig_map:
                for o_idx in orig_map[text]:
                    for f_idx in f_indices:
                        if o_idx not in matched_orig and f_match[f_idx] == -1:
                            f_match[f_idx] = o_idx
                            matched_orig.add(o_idx)
                            break  # 这个段落已匹配，跳出内层循环
        
        # 2. 相似匹配（支持一对多关系的改进算法）
        # 首先收集所有可能的匹配
        match_candidates = []
        for f_idx in range(len(final_paras)):
            if f_match[f_idx] != -1:
                continue
            
            for o_idx in range(len(orig_paras)):
                if o_idx in matched_orig:
                    continue
                
                ratio = difflib.SequenceMatcher(None,
                    orig_paras[o_idx]['text'],
                    final_paras[f_idx]['text']
                ).ratio()
                
                if ratio >= PARA_SIM_THRESHOLD:
                    # 添加位置接近度权重
                    position_score = 1.0 / (abs(o_idx - f_idx) + 1)
                    total_score = ratio * 0.7 + position_score * 0.3
                    match_candidates.append((total_score, ratio, o_idx, f_idx))
        
        # 按总分排序
        match_candidates.sort(reverse=True, key=lambda x: x[0])
        
        # 处理一对多匹配：允许一个终文档段落匹配多个原文档段落
        # 但一个原文档段落只能匹配一个终文档段落
        for total_score, ratio, o_idx, f_idx in match_candidates:
            if o_idx in matched_orig:
                continue
            
            # 修改：只在完全相同时跳过重复段落，相似匹配应该允许
            f_text = final_paras[f_idx]['text']
            o_text = orig_paras[o_idx]['text']
            
            # 如果是完全相同的文本，应用重复段落规则
            if f_text == o_text:
                f_text_count = sum(1 for p in final_paras if p['text'] == f_text)
                
                if f_text_count > 1:
                    # 检查这个文本是否是第一次出现
                    first_occurrence = True
                    for i in range(f_idx):
                        if final_paras[i]['text'] == f_text:
                            first_occurrence = False
                            break
                    
                    if not first_occurrence:
                        # 重复的完全相同的终文档段落，跳过匹配
                        continue
            
            # 如果这个终文档段落已经有匹配，检查是否应该添加额外的原文档段落
            # 修改：更严格的一对多匹配条件，只在真正需要合并时使用
            if f_match[f_idx] != -1:
                existing_o_idx = f_match[f_idx]
                
                # 检查是否应该创建一对多匹配
                should_create_one_to_many = False
                
                # 情况1：已存在一对多匹配，检查是否可以添加
                if isinstance(existing_o_idx, list):
                    # 如果与原列表中的段落相邻，可以添加
                    min_idx = min(existing_o_idx)
                    max_idx = max(existing_o_idx)
                    if (min_idx - 1 <= o_idx <= max_idx + 1):
                        should_create_one_to_many = True
                # 情况2：已存在一对一匹配，检查是否可以升级为一对多
                else:
                    # 只允许相邻段落创建一对多匹配，且相似度要足够高
                    if abs(o_idx - existing_o_idx) == 1 and ratio >= 0.6:  # 更严格的条件
                        should_create_one_to_many = True
                
                if should_create_one_to_many:
                    # 创建一对多匹配关系
                    if isinstance(existing_o_idx, list):
                        f_match[f_idx].append(o_idx)
                    else:
                        f_match[f_idx] = [existing_o_idx, o_idx]
                    matched_orig.add(o_idx)
                    # print(f"一对多匹配: 终段落[{f_idx}] 匹配 原段落{existing_o_idx}和{o_idx}")
                else:
                    # 不创建一对多匹配，让这个原段落匹配其他终段落
                    continue
            else:
                # 一对一匹配
                f_match[f_idx] = o_idx
                matched_orig.add(o_idx)
        
        # 3. 按终文档顺序输出 - 修复删除段落顺序问题
        processed_orig = set()  # 已处理的原文档段落索引
        next_orig_idx = 0  # 下一个待处理的原文档段落索引
        
        for f_idx in range(len(final_paras)):
            o_idx = f_match[f_idx]
            final_text = final_paras[f_idx]['text']
            
            # 终稿为空段落 → 保留空段落
            if not final_text:
                result_doc.add_paragraph()
                continue
            
            if o_idx == -1:
                # 新增段落
                p = result_doc.add_paragraph()
                run = p.add_run(final_text)
                run.font.color.rgb = RGBColor(255, 0, 0)
            else:
                # 处理一对多匹配
                if isinstance(o_idx, list):
                    # 先输出 o_idx 列表中第一个索引之前的未处理段落（删除的）
                    first_o_idx = min(o_idx)
                    while next_orig_idx < first_o_idx:
                        # 检查这个段落是否已经被匹配
                        if next_orig_idx not in matched_orig:
                            orig_del_text = orig_paras[next_orig_idx]['text']
                            if orig_del_text:
                                p = result_doc.add_paragraph()
                                run = p.add_run(orig_del_text)
                                run.font.color.rgb = RGBColor(0, 0, 255)
                                run.font.strike = True
                        next_orig_idx += 1
                    
                    # 合并多个原文档段落与一个终文档段落对比
                    p = result_doc.add_paragraph()
                    
                    # 合并所有原文档段落的文本
                    combined_orig_text = ""
                    for idx in o_idx:
                        if idx not in processed_orig:
                            combined_orig_text += orig_paras[idx]['text']
                            processed_orig.add(idx)
                            if idx >= next_orig_idx:
                                next_orig_idx = idx + 1
                    
                    # 进行对比
                    sentence_level_diff(combined_orig_text, final_text, p, SENTENCE_SIM_THRESHOLD)
                else:
                    # 一对一匹配 - 先输出 o_idx 之前的未处理段落（删除的）
                    while next_orig_idx < o_idx:
                        # 检查这个段落是否已经被匹配（在一对多匹配中可能已被匹配）
                        if next_orig_idx not in matched_orig:
                            orig_del_text = orig_paras[next_orig_idx]['text']
                            if orig_del_text:
                                p = result_doc.add_paragraph()
                                run = p.add_run(orig_del_text)
                                run.font.color.rgb = RGBColor(0, 0, 255)
                                run.font.strike = True
                        next_orig_idx += 1
                    
                    if o_idx in processed_orig:
                        # 如果这个原始段落已经被处理过，就当作新增段落处理
                        p = result_doc.add_paragraph()
                        run = p.add_run(final_text)
                        run.font.color.rgb = RGBColor(255, 0, 0)
                    else:
                        # 处理当前匹配的段落
                        processed_orig.add(o_idx)
                        next_orig_idx = o_idx + 1
                        
                        orig_text = orig_paras[o_idx]['text']
                        if orig_text == final_text:
                            result_doc.add_paragraph(orig_text)
                        else:
                            # 根据整体相似度决定比对方式
                            p = result_doc.add_paragraph()
                            sentence_level_diff(orig_text, final_text, p, SENTENCE_SIM_THRESHOLD)
        
        # 4. 输出剩余的删除段落（跳过空段落）
        while next_orig_idx < len(orig_paras):
            # 检查这个段落是否已经被匹配
            if next_orig_idx not in matched_orig:
                orig_del_text = orig_paras[next_orig_idx]['text']
                if orig_del_text:
                    p = result_doc.add_paragraph()
                    run = p.add_run(orig_del_text)
                    run.font.color.rgb = RGBColor(0, 0, 255)
                    run.font.strike = True
            next_orig_idx += 1
        
        result_doc.save(output_path)
        return True, "短句级比对"
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, str(e)


def check_and_convert_file(file_path):
    """检查文件类型，doc 转换为 docx"""

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.doc':
        doc_dir = os.path.dirname(file_path)
        doc_to_docx(doc_dir)
        docx_path = os.path.splitext(file_path)[0] + '.docx'
        if os.path.exists(docx_path):
            return docx_path
        print(f"警告：doc 文件转换失败: {file_path}")
        return None
    elif ext == '.docx':
        return file_path
    else:
        print(f"错误：不支持的文件类型 '{ext}'，仅支持 .doc 和 .docx")
        return None


def main(workdir, original_path=None, final_path=None):
    """主函数
    Args:
        workdir: 工作目录
        original_path: 直接传入的原稿路径（可选）
        final_path: 直接传入的终稿路径（可选）
    """ 
    
    # 判断传入的是文件还是目录
    if original_path and final_path:
        if not os.path.exists(original_path):
            print(f"文件不存在: {original_path}")
            return
        if not os.path.exists(final_path):
            print(f"文件不存在: {final_path}")
            return
        original = check_and_convert_file(original_path)
        final = check_and_convert_file(final_path)
    else:
        # 传入目录，调用 find_docx_files 让用户选择
        original, final = find_docx_files(workdir)
        if not original or not final:
            return
    
    if not original or not final:
        print("无法比较：请检查文件格式")
        return

    print(f"原稿: {os.path.basename(original)}")
    print(f"终稿: {os.path.basename(final)}")
    
    # 确定输出文件名
    output_name = f"对比标注-{os.path.basename(original)}"
    print("开始比较...")
    
    success, result_msg = compare_with_python(original, final, os.path.join(workdir, output_name))
    
    if success:
        print(f"\n比较完成!")
        print(f"方法: {result_msg}")
        print(f"结果保存至: {os.path.normpath(os.path.join(workdir, output_name))}")
    else:
        print(f"\n比较失败: {result_msg}")


if __name__ == "__main__":
    import sys
    original_path = None
    final_path = None
    
    # 解析命令行参数
    # sys.argv[0] 是脚本路径
    # 如果参数数量 >= 3：第一个文件路径和第二个文件路径
    # 如果参数数量 == 2：工作目录
    if len(sys.argv) >= 3:
        # 传入两个文档路径（脚本路径 + 文件1 + 文件2）
        original_path = sys.argv[1]
        final_path = sys.argv[2]
        workdir = os.path.dirname(original_path)
    elif len(sys.argv) == 2:
        # 传入工作目录（脚本路径 + 工作目录）
        workdir = sys.argv[1]
    else:
        workdir = os.path.dirname(__file__)
    
    main(workdir, original_path, final_path)
