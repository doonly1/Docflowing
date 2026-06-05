/**
 * postinstall 脚本：将 npm 前端依赖拷贝到 ui/lib/
 * 这样 Flask 静态文件服务可以访问这些库文件
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const NODE_MODULES = path.join(ROOT, 'node_modules');
const LIB_DIR = path.join(ROOT, 'ui', 'lib');

// 需要拷贝的包及其所需文件
const PACKAGES = {
    'quill': {
        files: [
            'dist/quill.js',
            'dist/quill.snow.css'
        ]
    },
    'marked': {
        files: [
            'marked.min.js'
        ]
    },
    'turndown': {
        files: [
            'dist/turndown.js'
        ]
    }
};

function copyLibs() {
    // 确保 lib 目录存在
    if (!fs.existsSync(LIB_DIR)) {
        fs.mkdirSync(LIB_DIR, { recursive: true });
    }

    for (const [pkgName, pkgConfig] of Object.entries(PACKAGES)) {
        const pkgDir = path.join(LIB_DIR, pkgName);
        if (!fs.existsSync(pkgDir)) {
            fs.mkdirSync(pkgDir, { recursive: true });
        }

        for (const file of pkgConfig.files) {
            const src = path.join(NODE_MODULES, pkgName, file);
            const dest = path.join(pkgDir, file);
            const destDir = path.dirname(dest);

            if (!fs.existsSync(destDir)) {
                fs.mkdirSync(destDir, { recursive: true });
            }

            if (fs.existsSync(src)) {
                fs.copyFileSync(src, dest);
                console.log(`[copy-libs] ✓ ${pkgName}/${file}`);
            } else {
                console.warn(`[copy-libs] ✗ 源文件不存在: ${src}`);
            }
        }
    }

    console.log('[copy-libs] 完成');
}

copyLibs();
