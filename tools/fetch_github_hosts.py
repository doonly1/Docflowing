# ================================
# GitHub Hosts Updater (Python Version)
# 用法: python fetch_github_hosts.py [--silent]
# ================================

import os
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
