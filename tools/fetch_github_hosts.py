# ================================
# GitHub Hosts Updater (Python Version)
# 用法: python fetch_github_hosts.py [--silent]
# ================================

import os
import re
import sys
import ctypes
import urllib.request
import urllib.error

# 配置
HOSTS_FILE = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), r'System32\drivers\etc\hosts')
REMOTE_URL = "https://raw.hellogithub.com/hosts"
START_MARKER = "# GitHub520 Host Start"
END_MARKER = "# Github520 Host End"


def is_admin():
    """检查是否为管理员"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def run_as_admin():
    """以管理员身份重新运行（保留 --silent 参数）"""
    args = f'"{sys.argv[0]}"'
    if "--silent" in sys.argv:
        args += " --silent"
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 0)


def download_file(url):
    """下载文件内容"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                return response.read().decode('utf-8')
    except (urllib.error.URLError, Exception):
        pass
    return None


def validate_hosts_content(content: str) -> tuple[bool, str]:
    """校验下载的 hosts 内容安全性和格式

    返回 (是否有效, 错误消息)。
    正常内容样例：'140.82.112.0 github.com'
    """
    if not content:
        return False, "下载内容为空"

    # 内容大小限制：正常 GitHub520 hosts 不超过 200KB
    if len(content) > 200 * 1024:
        return False, f"内容过大（{len(content)} 字节），疑似恶意数据"

    # 校验每一行
    _ip_pattern = re.compile(r'^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+(\S+)\s*$')
    private_prefixes = ('10.', '172.16.', '172.17.', '172.18.', '172.19.',
                       '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                       '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                       '172.30.', '172.31.', '192.168.', '127.', '0.')
    valid_line_count = 0
    for line_no, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue  # 空行和注释允许
        m = _ip_pattern.match(stripped)
        if not m:
            return False, f"第 {line_no} 行格式无效: {stripped[:60]}"
        ip, domain = m.group(1), m.group(2)
        # 拒绝私有/回环 IP
        if ip.startswith(private_prefixes) or ip == '255.255.255.255':
            return False, f"第 {line_no} 行使用了私有/回环 IP: {ip}"
        valid_line_count += 1

    if valid_line_count == 0:
        return False, "未找到有效的 hosts 记录"

    return True, ""


def show_message(title, message, style=0):
    """显示消息框 (0=信息, 16=错误)，仅非静默模式"""
    if "--silent" not in sys.argv:
        ctypes.windll.user32.MessageBoxW(0, message, title, style)


def main():
    silent = "--silent" in sys.argv

    # 检查管理员权限
    if not is_admin():
        run_as_admin()
        sys.exit(0)

    # Step 1: 读取 hosts 文件并移除旧记录
    new_content = ""
    skip = False

    if os.path.exists(HOSTS_FILE):
        try:
            with open(HOSTS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.rstrip('\r\n')
                    if line == START_MARKER:
                        skip = True
                    elif line == END_MARKER:
                        skip = False
                    elif not skip:
                        new_content += line + '\n'
        except Exception as e:
            if not silent:
                show_message("GitHub Hosts", f"读取 hosts 文件失败: {e}", 16)
            sys.exit(1)

    # Step 2: 下载最新的 GitHub Hosts
    downloaded_content = download_file(REMOTE_URL)

    if downloaded_content is None:
        if not silent:
            show_message("GitHub Hosts", "下载 hosts 失败!", 16)
        sys.exit(1)

    # Step 2.5: 校验下载内容的格式和安全性
    valid, err_msg = validate_hosts_content(downloaded_content)
    if not valid:
        if not silent:
            show_message("GitHub Hosts", f"Hosts 内容校验失败: {err_msg}，拒绝写入", 16)
        sys.exit(1)

    # 合并内容
    new_content += downloaded_content

    # Step 3: 写入 hosts 文件
    try:
        with open(HOSTS_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)
        if not silent:
            show_message("GitHub Hosts", "Hosts 文件更新成功!", 0)
    except Exception as e:
        if not silent:
            show_message("GitHub Hosts", f"写入 hosts 文件失败: {e}", 16)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
