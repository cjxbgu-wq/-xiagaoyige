#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VCam 构建与部署脚本
- 支持本地开发构建和发布构建
- 自动运行混淆生成
- 构建产物输出到指定目录
- 可选推送到 Git 仓库
"""

import os
import sys
import subprocess
import shutil
import argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.absolute()
BUILD_DIR = ROOT / "build_output"
OBFUSCATED_DIR = ROOT / "obfsrc"
THEOS = os.environ.get("THEOS", "/opt/theos")

def run_cmd(cmd, cwd=None, env=None, check=True):
    """运行命令并返回结果"""
    print(f"[CMD] {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd or ROOT, 
                           env=env or os.environ, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败 (code={result.returncode}): {cmd}")
    return result

def clean_build():
    """清理构建产物"""
    dirs_to_clean = [
        ROOT / "obj",
        ROOT / "packages",
        ROOT / ".theos",
        BUILD_DIR,
    ]
    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print(f"已清理: {d}")

def generate_obfuscation():
    """生成混淆源码"""
    print("=== 生成混淆源码 ===")
    run_cmd(f"python {ROOT}/gen_obf_src.py")
    print("混淆源码生成完成")

def build_theos(final_package=False, output_dir=None):
    """使用 Theos 构建 iOS Tweak"""
    print(f"=== 构建 Theos Tweak (FINALPACKAGE={'1' if final_package else '0'}) ===")
    
    env = os.environ.copy()
    env["THEOS"] = THEOS
    env["FINALPACKAGE"] = "1" if final_package else "0"
    
    # 设置输出目录
    if output_dir:
        env["THEOS_PACKAGE_DIR"] = str(output_dir)
    
    # 运行 make
    run_cmd("make clean", env=env)
    run_cmd("make", env=env)
    
    # 查找生成的 .deb 文件
    pkg_dir = Path(env.get("THEOS_PACKAGE_DIR", ROOT / "packages"))
    deb_files = list(pkg_dir.glob("*.deb"))
    
    if deb_files:
        print(f"构建成功，生成文件:")
        for f in deb_files:
            print(f"  {f}")
        return deb_files
    else:
        print("警告: 未找到生成的 .deb 文件")
        return []

def build_python_license_tool(output_dir):
    """使用 PyInstaller 打包 Python 卡密生成工具"""
    print("=== 打包 Python 卡密生成工具 ===")
    
    # 检查 PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("安装 PyInstaller...")
        run_cmd(f"{sys.executable} -m pip install pyinstaller")
    
    # 使用静态 spec 文件
    spec_path = ROOT / "license_generator.spec"
    if not spec_path.exists():
        raise FileNotFoundError(f"Spec 文件不存在: {spec_path}")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    run_cmd(f'pyinstaller --clean --distpath "{output_dir}" --workpath "{output_dir}/build" "{spec_path}"')
    
    exe_path = output_dir / "vcam_license_generator.exe"
    if exe_path.exists():
        print(f"打包成功: {exe_path}")
        return [exe_path]
    else:
        print("警告: 未找到生成的 exe 文件")
        return []

def copy_artifacts(deb_files, exe_files, output_dir):
    """复制构建产物到输出目录"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    artifacts = []
    
    for f in deb_files:
        dst = output_dir / f.name
        shutil.copy2(f, dst)
        artifacts.append(dst)
        print(f"复制: {dst}")
    
    for f in exe_files:
        dst = output_dir / f.name
        shutil.copy2(f, dst)
        artifacts.append(dst)
        print(f"复制: {dst}")
    
    # 生成构建信息文件
    info_file = output_dir / "build_info.txt"
    with open(info_file, 'w', encoding='utf-8') as f:
        f.write(f"VCam Build Info\n")
        f.write(f"================\n")
        f.write(f"Build Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Git Commit: {get_git_commit()}\n")
        f.write(f"Public Key: 0482aee00557c5ddf34e27610473bb0479272657c0a8c70bc143f21513c704c5c80a26e55916d96d4bd5550a0890f5e23085e40792663841258f3dd9076664ef93\n")
        f.write(f"\nArtifacts:\n")
        for a in artifacts:
            f.write(f"  {a.name}\n")
    
    print(f"构建信息已写入: {info_file}")
    return artifacts

def get_git_commit():
    """获取当前 Git 提交哈希"""
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], 
                               cwd=ROOT, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()[:8]
    except:
        pass
    return "unknown"

def push_to_git(artifacts, repo_url=None, branch="main"):
    """推送构建产物到 Git 仓库"""
    print("=== 推送到 Git 仓库 ===")
    
    if not repo_url:
        # 尝试从 git config 获取
        result = subprocess.run(["git", "config", "--get", "remote.origin.url"], 
                               cwd=ROOT, capture_output=True, text=True)
        if result.returncode == 0:
            repo_url = result.stdout.strip()
    
    if not repo_url:
        print("未配置远程仓库，跳过推送")
        return
    
    # 检查是否有变更
    run_cmd("git status")
    
    # 添加构建产物 (如果配置了发布分支)
    # 这里演示推送到单独的 releases 分支或 tag
    tag_name = f"build-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    try:
        run_cmd(f"git tag {tag_name}")
        run_cmd(f"git push origin {tag_name}")
        print(f"已创建并推送标签: {tag_name}")
    except:
        print("标签推送失败（可能已存在或无权限）")

def main():
    parser = argparse.ArgumentParser(description="VCam 构建与部署脚本")
    parser.add_argument("--final", action="store_true", help="发布构建 (FINALPACKAGE=1)")
    parser.add_argument("--clean", action="store_true", help="构建前清理")
    parser.add_argument("--output", default=str(BUILD_DIR), help="输出目录")
    parser.add_argument("--push", action="store_true", help="构建后推送到 Git")
    parser.add_argument("--repo", help="Git 仓库地址")
    parser.add_argument("--skip-theos", action="store_true", help="跳过 Theos 构建")
    parser.add_argument("--skip-python", action="store_true", help="跳过 Python 打包")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    
    try:
        if args.clean:
            clean_build()
        
        # 1. 生成混淆源码
        generate_obfuscation()
        
        # 2. 构建 Theos Tweak
        deb_files = []
        if not args.skip_theos:
            deb_files = build_theos(final_package=args.final, output_dir=output_dir)
        
        # 3. 打包 Python 工具
        exe_files = []
        if not args.skip_python:
            exe_files = build_python_license_tool(output_dir)
        
        # 4. 复制产物
        artifacts = copy_artifacts(deb_files, exe_files, output_dir)
        
        # 5. 推送到 Git
        if args.push:
            push_to_git(artifacts, args.repo)
        
        print("\n=== 构建完成 ===")
        print(f"输出目录: {output_dir}")
        for a in artifacts:
            print(f"  {a.name}")
        
    except Exception as e:
        print(f"\n构建失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()