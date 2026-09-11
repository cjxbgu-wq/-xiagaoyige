#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VCam 卡密生成器 v3 (HMAC-SHA256 · 离线验签 · 短密钥)
参考设计: 卡密系统/PC端/keygen_hex.py

卡密格式: XXXX-XXXX-XXXX-XXXX (16位十六进制 = 8字节)
内部结构:
  byte0      : 时长计划 (0=时卡 1=天卡 2=月卡 3=永久)
  byte1-2    : 随机 nonce (2字节)
  byte3-7    : HMAC-SHA256(SECRET, 前3字节) 截取前5字节

SECRET 与 iOS 补丁 CardKeyGuard.xm 的 gVPMSecret[] 完全一致!
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import time

# 32字节 SECRET — 与 CardKeyGuard.xm 的 gVPMSecret[] 完全一致!
SECRET = bytes([
    0x51, 0xC8, 0x2E, 0xA9, 0xF4, 0x17, 0x63, 0xBB,
    0x90, 0x5D, 0x08, 0xE6, 0x2F, 0x74, 0xAD, 0xC1,
    0x33, 0x69, 0xF0, 0x1B, 0x87, 0xD4, 0x4A, 0x92,
    0x6E, 0x05, 0xB3, 0x78, 0xEC, 0x59, 0x20, 0xFF,
])
assert len(SECRET) == 32

PLANS = {"hour": 0, "day": 1, "month": 2, "forever": 3}
PLAN_CN = {"hour": "时卡(1小时)", "day": "天卡(1天)", "month": "月卡(30天)", "forever": "永久卡"}

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys_db.json")


def _load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"keys": {}}


def _save_db(db):
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_FILE)


def make_key(plan: str) -> str:
    """生成一张卡密"""
    plan_id = PLANS[plan]
    while True:
        nonce = secrets.token_bytes(2)
        msg = bytes([plan_id]) + nonce
        mac = hmac.new(SECRET, msg, hashlib.sha256).digest()[:5]
        raw = msg + mac  # 8 bytes
        hex16 = raw.hex().upper()
        key = "-".join(hex16[i:i + 4] for i in range(0, 16, 4))
        db = _load_db()
        if key not in db.get("keys", {}):
            break
    db.setdefault("keys", {})[key] = {
        "plan": plan,
        "created_at": int(time.time()),
        "note": "",
    }
    _save_db(db)
    return key


def verify_key(key: str):
    """验证卡密"""
    hx = key.strip().upper().replace("-", "")
    if len(hx) != 16 or any(c not in "0123456789ABCDEF" for c in hx):
        return None, "格式错误: 需16位十六进制"
    raw = bytes.fromhex(hx)
    if raw[0] > 3:
        return None, "未知计划类型"
    expect = hmac.new(SECRET, raw[:3], hashlib.sha256).digest()[:5]
    if not hmac.compare_digest(raw[3:], expect):
        return None, "签名验证失败"
    name = [k for k, v in PLANS.items() if v == raw[0]][0]
    return name, None


def cmd_gen(plan: str, count: int, out_file: str = None):
    keys = [make_key(plan) for _ in range(count)]
    # 自检
    for k in keys:
        p, err = verify_key(k)
        assert p == plan and err is None, f"自检失败: {k}"
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(f"# {time.strftime('%Y-%m-%d %H:%M:%S')}  {PLAN_CN[plan]}  数量={count}\n")
            f.write("\n".join(keys) + "\n")
        print(f"OK 已生成 {count} 张 {PLAN_CN[plan]} -> {out_file} (自检通过)")
    else:
        print(f"# {PLAN_CN[plan]} x{count} (已入库, 自检通过)")
        print("\n".join(keys))


def cmd_list():
    db = _load_db()
    if not db.get("keys"):
        print("(空) 还没有生成过卡密")
        return
    print(f"{'卡密':<22} 类型           生成时间")
    for k, v in sorted(db["keys"].items(), key=lambda x: -x[1]["created_at"]):
        ts = time.strftime("%m-%d %H:%M", time.localtime(v["created_at"]))
        print(f"{k:<22} {PLAN_CN[v['plan']]:<14} {ts}")


def cmd_del(key: str):
    db = _load_db()
    k = key.strip().upper()
    if k not in db.get("keys", {}):
        print("FAIL 卡密不存在")
        sys.exit(1)
    del db["keys"][k]
    _save_db(db)
    print("OK 已从台账删除", k)


def cmd_verify(key: str):
    p, err = verify_key(key)
    if err:
        print(f"FAIL {err}")
        sys.exit(1)
    print(f"OK 有效卡密  plan={PLAN_CN[p]}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("用法:")
        print("  python license_generator.py gen hour|day|month|forever <数量> [--out 文件]")
        print("  python license_generator.py list")
        print("  python license_generator.py del <卡密>")
        print("  python license_generator.py verify <卡密>")
        print("")
        print("示例:")
        print("  python license_generator.py gen month 5 --out cards.txt")
        print("  python license_generator.py verify A1B2-C3D4-E5F6-7890")
        return

    cmd = sys.argv[1]
    if cmd == "gen":
        if len(sys.argv) < 4:
            print("用法: gen <plan> <count> [--out file]")
            return
        plan = sys.argv[2]
        count = int(sys.argv[3])
        out_file = None
        if "--out" in sys.argv:
            idx = sys.argv.index("--out")
            if idx + 1 < len(sys.argv):
                out_file = sys.argv[idx + 1]
        cmd_gen(plan, count, out_file)
    elif cmd == "list":
        cmd_list()
    elif cmd == "del":
        if len(sys.argv) < 3:
            print("用法: del <卡密>")
            return
        cmd_del(sys.argv[2])
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("用法: verify <卡密>")
            return
        cmd_verify(sys.argv[2])
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()