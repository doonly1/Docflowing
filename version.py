"""Docflowing 版本单一来源。

全项目只有这里定义版本号，以下位置全部引用本模块，禁止再写死：

- ``build-desktop.py`` 生成 NSIS 脚本时的 ``!define PRODUCT_VERSION``
- ``desktop_app.DesktopAPI.getAppVersion()`` 返回给前端的运行时版本
- ``make_update_manifest.py`` 生成更新清单 ``version.json``
- ``.github/workflows/release.yml`` 校验 git tag 与版本号一致

发版流程：
    1. 改这里的 ``APP_VERSION``（语义化版本 major.minor.patch）
    2. 提交并合并到 main
    3. ``git tag v<APP_VERSION> && git push origin v<APP_VERSION>``
    4. CI 自动构建安装包、生成 version.json、发布 Release

版本号必须是 ``X.Y.Z`` 三段纯数字，更新器依赖它做版本比对。
"""

APP_VERSION = '1.0.5'

# 更新通道。'stable' 只接收 stable 清单；'beta' 可接收 beta 与 stable。
UPDATE_CHANNEL = 'stable'


def parse_version(text):
    """把版本字符串解析成可比较的整数元组。

    容错处理常见的非标准写法：前导 ``v``、预发布后缀 ``-beta.1``、缺位补 0。
    解析失败返回 ``(0,)``，保证比较永不抛异常（更新检查不能因为怪版本号崩掉）。

    >>> parse_version('v1.2.3') > parse_version('1.2.10')
    False
    >>> parse_version('1.2.3-beta.1') < parse_version('1.2.3')
    True
    """
    if text is None:
        return (0,)
    s = str(text).strip()
    if s[:1] in ('v', 'V'):
        s = s[1:]

    # 预发布版本低于同号正式版：拆出来单独记一个标记位
    pre = 1
    for sep in ('-', '+'):
        if sep in s:
            s, _tail = s.split(sep, 1)
            pre = 0
            break

    parts = []
    for chunk in s.split('.'):
        digits = ''
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)

    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3]) + (pre,)


def compare_versions(a, b):
    """比较两个版本号，返回 -1 / 0 / 1。"""
    ta, tb = parse_version(a), parse_version(b)
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


def format_version():
    """返回规范化的版本字符串（去掉可能存在的 v 前缀）。"""
    return APP_VERSION.lstrip('vV')
