#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VCam 卡密生成系统
- 使用 ECDSA P-256 (secp256r1) 签名
- 与源码验证机制完全互通
- 支持永久卡和月卡
"""

import sys
import os
import hashlib
import base64
import struct
import csv
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature, decode_dss_signature
from cryptography.exceptions import InvalidSignature

# ============================================================
# 常量配置（与源码严格一致）
# ============================================================
T_SALT_HEX = "7ecfba852c100ab4228ac14f062f737c"  # 16 字节
T_SALT = bytes.fromhex(T_SALT_HEX)
MAGIC_VALUE = 0x3FA7C2E1  # T[0] 魔数
T_TABLE_SIZE = 18  # 18 个 u32 = 72 字节

# 默认 T 表参数（功能参数真值）
DEFAULT_T_TRUE = [
    0x3FA7C2E1,      # idx0: 魔数
    0xFF64B84C,      # idx1: 打光色 R
    0xFF8C4232,      # idx2: 打光色 G
    0xFF3A7CA5,      # idx3: 打光色 B
    0x00000064,      # idx4: 打光强度 (100)
    0x00000030,      # idx5: 打光直径 (48)
    0x00000064,      # idx6: 打光羽化 (100)
    0x0000001E,      # idx7: HSV 门限 (30)
    0x0000000A,      # idx8: 计票阈值 (10)
    0x00000064,      # idx9: zoom x100 (100 = 1.00x)
    0x00000064,      # idx10: zoom y100
    0x00000064,      # idx11: zoom z100
    0x00000000,      # idx12: pan x100
    0x00000000,      # idx13: pan y100
    0x00000001,      # idx14: 旋转步进 (1 = 90度)
    0x00000064,      # idx15: 羽化分子 (100)
    0x00000064,      # idx16: 羽化分母 (100)
    0x00000000,      # idx17: 校验和 (XOR of idx0..16)
]

# ============================================================
# 加密工具函数
# ============================================================
def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def u32be(val: int) -> bytes:
    return struct.pack('>I', val & 0xFFFFFFFF)

def u32_from_bytes(data: bytes, offset: int) -> int:
    return struct.unpack('>I', data[offset:offset+4])[0]

def compute_dev_hash32(device_code: str) -> list:
    """计算 devHash32 = SHA256(device_code) -> 8×u32(BE)"""
    dc_bytes = device_code.encode('ascii')
    dev_hash = sha256(dc_bytes)
    dev32 = []
    for i in range(8):
        val = (dev_hash[i*4] << 24) | (dev_hash[i*4+1] << 16) | \
              (dev_hash[i*4+2] << 8) | dev_hash[i*4+3]
        dev32.append(val)
    return dev32

def compute_k(device_code: str) -> bytes:
    """K = SHA256(device_code || T_SALT)"""
    dc_bytes = device_code.encode('ascii')
    buf = dc_bytes + T_SALT
    return sha256(buf)

def encrypt_t_table(t_true: list, device_code: str) -> bytes:
    """
    加密 T 表生成 T_enc (72 字节)
    逆向: T_enc[i] = T[i] ^ stream[i] ^ dev32[i%8]
    """
    k = compute_k(device_code)
    dev32 = compute_dev_hash32(device_code)
    
    t_enc = bytearray(72)
    
    for blk in range(3):  # 3 块
        # ctr = K || u32be(block_index)
        ctr = k + u32be(blk)
        st = sha256(ctr)  # 32 字节
        
        for j in range(6):  # 每块 6 个 u32
            idx = blk * 6 + j
            # stream word
            s = u32_from_bytes(st, j * 4)
            # T_enc = T ^ stream ^ dev32
            t_enc_val = t_true[idx] ^ s ^ dev32[idx % 8]
            struct.pack_into('>I', t_enc, idx * 4, t_enc_val & 0xFFFFFFFF)
    
    return bytes(t_enc)

def decrypt_t_table(t_enc: bytes, device_code: str) -> list:
    """解密 T 表（用于验证）"""
    k = compute_k(device_code)
    dev32 = compute_dev_hash32(device_code)
    
    t_true = []
    enc_bytes = t_enc
    
    for blk in range(3):
        ctr = k + u32be(blk)
        st = sha256(ctr)
        
        for j in range(6):
            idx = blk * 6 + j
            s = u32_from_bytes(st, j * 4)
            e = u32_from_bytes(enc_bytes, idx * 4)
            t_val = e ^ s ^ dev32[idx % 8]
            t_true.append(t_val)
    
    return t_true

# ============================================================
# 签名相关
# ============================================================
def load_private_key(pem_path: str) -> ec.EllipticCurvePrivateKey:
    with open(pem_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(
            f.read(),
            password=None
        )
    return private_key

def sign_message(private_key: ec.EllipticCurvePrivateKey, message: bytes) -> bytes:
    """签名并返回 DER 编码签名"""
    signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
    # cryptography 返回的已经是 DER 格式
    return signature

def verify_signature(public_key: ec.EllipticCurvePublicKey, message: bytes, signature: bytes) -> bool:
    """验证签名"""
    try:
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False

def public_key_to_x962_hex(public_key: ec.EllipticCurvePublicKey) -> str:
    """获取 X9.62 未压缩公钥 hex (65 字节，以 04 开头)"""
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    return pub_bytes.hex()

# ============================================================
# 许可证生成核心
# ============================================================
def generate_license_blob(device_code: str, private_key: ec.EllipticCurvePrivateKey, 
                          t_true: list = None, expiry_days: int = None) -> str:
    """
    生成许可证 blob
    格式 v2 (永久卡): base64(DER签名).base64(T_enc)
    格式 v3 (月卡): base64(DER签名).base64(T_enc).base64(expiryInfo)
    
    Args:
        device_code: 16 字符大写十六进制设备码
        private_key: ECDSA 私钥
        t_true: 自定义 T 表参数 (18 个 u32)，None 则用默认值
        expiry_days: 过期天数，None 表示永久卡
    
    Returns:
        license blob 字符串
    """
    # 验证设备码
    if len(device_code) != 16:
        raise ValueError("设备码必须是 16 字符十六进制字符串")
    
    # 使用默认或自定义 T 表
    if t_true is None:
        t_true = DEFAULT_T_TRUE.copy()
    else:
        t_true = t_true.copy()
    
    # 计算校验和
    checksum = 0
    for i in range(17):
        checksum ^= t_true[i]
    t_true[17] = checksum
    
    # 加密 T 表
    t_enc = encrypt_t_table(t_true, device_code)
    
    # 构造签名消息：设备码(16 ascii) || T_enc(72 字节)
    message = device_code.encode('ascii') + t_enc
    
    # 签名
    signature = sign_message(private_key, message)
    
    # 验证签名长度 (DER 格式 P-256 通常 66-72 字节)
    if not (64 <= len(signature) <= 72):
        raise ValueError(f"签名长度异常: {len(signature)} 字节")
    if signature[0] != 0x30:
        raise ValueError("签名不是 DER 格式 (首字节应为 0x30)")
    
    sig_b64 = base64.b64encode(signature).decode('ascii')
    t_enc_b64 = base64.b64encode(t_enc).decode('ascii')
    
    # 月卡: 添加 expiryInfo (base64 编码的 "expiryDays:0" 占位，激活时填充激活时间)
    if expiry_days is not None and expiry_days > 0:
        import json
        expiry_info = json.dumps({"expiryDays": expiry_days, "activatedAt": 0}).encode('ascii')
        expiry_b64 = base64.b64encode(expiry_info).decode('ascii')
        return f"{sig_b64}.{t_enc_b64}.{expiry_b64}"
    
    # 永久卡: v2 格式
    return f"{sig_b64}.{t_enc_b64}"

def verify_license_blob(blob: str, device_code: str, public_key: ec.EllipticCurvePublicKey) -> tuple:
    """
    验证许可证 blob
    Returns: (bool, dict) - (验证是否通过, 解析出的信息)
    """
    try:
        # 解析 blob (支持 v2: sig.t_enc 和 v3: sig.t_enc.expiryInfo)
        parts = blob.split('.')
        if len(parts) not in (2, 3):
            return False, {"error": f"blob 格式错误：段数 {len(parts)} 不支持 (需 2 或 3)"}
        
        sig_b64, t_enc_b64 = parts[0], parts[1]
        expiry_info = None
        if len(parts) == 3:
            # v3 格式：解析 expiryInfo
            expiry_b64 = parts[2]
            try:
                import json
                expiry_json = base64.b64decode(expiry_b64).decode('ascii')
                expiry_info = json.loads(expiry_json)
            except Exception as e:
                return False, {"error": f"expiryInfo 解析失败: {str(e)}"}
        
        signature = base64.b64decode(sig_b64)
        t_enc = base64.b64decode(t_enc_b64)
        
        # 验证基础格式
        if len(t_enc) != 72:
            return False, {"error": f"T_enc 长度错误: {len(t_enc)} != 72"}
        if not (64 <= len(signature) <= 72):
            return False, {"error": f"签名长度错误: {len(signature)}"}
        if signature[0] != 0x30:
            return False, {"error": "签名非 DER 格式"}
        
        # 验证签名
        message = device_code.encode('ascii') + t_enc
        if not verify_signature(public_key, message, signature):
            return False, {"error": "ECDSA 验签失败"}
        
        # 解密 T 表
        t_true = decrypt_t_table(t_enc, device_code)
        
        # 验证魔数和校验和
        if t_true[0] != MAGIC_VALUE:
            return False, {"error": f"魔数校验失败: {hex(t_true[0])} != {hex(MAGIC_VALUE)}"}
        
        checksum = 0
        for i in range(17):
            checksum ^= t_true[i]
        if t_true[17] != checksum:
            return False, {"error": f"校验和失败: {hex(t_true[17])} != {hex(checksum)}"}
        
        # 解析参数
        info = {
            "valid": True,
            "magic": hex(t_true[0]),
            "light_color_r": t_true[1],
            "light_color_g": t_true[2],
            "light_color_b": t_true[3],
            "light_intensity": t_true[4],
            "light_diameter": t_true[5],
            "light_feather": t_true[6],
            "hsv_threshold": t_true[7],
            "vote_threshold": t_true[8],
            "zoom_x": t_true[9] / 100.0,
            "zoom_y": t_true[10] / 100.0,
            "zoom_z": t_true[11] / 100.0,
            "pan_x": t_true[12] / 100.0,
            "pan_y": t_true[13] / 100.0,
            "rotation_step": t_true[14],
            "feather_num": t_true[15],
            "feather_den": t_true[16],
            "checksum": hex(t_true[17]),
        }
        
        # 添加过期信息
        if expiry_info:
            info["expiryDays"] = expiry_info.get("expiryDays", 0)
            info["activatedAt"] = expiry_info.get("activatedAt", 0)
            info["isMonthly"] = True
        else:
            info["expiryDays"] = 0
            info["isMonthly"] = False
        
        return True, info
        
    except Exception as e:
        return False, {"error": f"验证异常: {str(e)}"}

# ============================================================
# 批量生成
# ============================================================
def batch_generate(device_code: str, private_key_path: str, count: int, 
                   license_type: str, expiry_days: int = None) -> list:
    """
    批量生成许可证
    """
    private_key = load_private_key(private_key_path)
    public_key = private_key.public_key()
    
    # 显示公钥信息
    pub_hex = public_key_to_x962_hex(public_key)
    print(f"使用公钥: {pub_hex}")
    print(f"设备码: {device_code}")
    print(f"生成数量: {count}")
    print(f"许可证类型: {license_type}")
    if expiry_days:
        print(f"有效天数: {expiry_days}")
    print("-" * 60)
    
    licenses = []
    for i in range(count):
        # 每个许可证可以使用不同的 T 表参数（通过添加序列号区分）
        t_custom = DEFAULT_T_TRUE.copy()
        t_custom[1] = (t_custom[1] + i) & 0xFFFFFFFF  # 稍微变化颜色区分
        
        blob = generate_license_blob(device_code, private_key, t_custom, expiry_days)
        
        # 验证生成的许可证
        valid, info = verify_license_blob(blob, device_code, public_key)
        status = "[OK]" if valid else "[FAIL]"
        
        licenses.append({
            "index": i + 1,
            "blob": blob,
            "valid": valid,
            "info": info
        })
        
        print(f"{status} [{i+1}/{count}] {blob[:50]}...")
    
    print("-" * 60)
    valid_count = sum(1 for l in licenses if l["valid"])
    print(f"生成完成: {valid_count}/{count} 个验证通过")
    
    return licenses

# ============================================================
# 导出 CSV
# ============================================================
def export_licenses_csv(licenses: list, filename: str, device_code: str, 
                         license_type: str, expiry_days: int = None):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Index", "License Blob", "Type", "Expiry Days", "Device Code", "Generated At"])
        for lic in licenses:
            writer.writerow([
                lic["index"],
                lic["blob"],
                license_type,
                expiry_days if expiry_days else "永久",
                device_code,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
    print(f"已导出 CSV: {filename}")

# ============================================================
# 主程序入口
# ============================================================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("用法:")
        print("  python license_generator.py <device_code> [options]")
        print("")
        print("选项:")
        print("  --count N         生成数量 (默认 100)")
        print("  --type TYPE       许可证类型: permanent|monthly (默认 permanent)")
        print("  --days N          月卡有效天数 (默认 30)")
        print("  --key PATH        私钥路径 (默认 ./license_priv_new.pem)")
        print("  --output FILE     导出 CSV 文件名")
        print("  --verify BLOB     验证单个 blob")
        print("")
        print("示例:")
        print("  python license_generator.py ABCDEF1234567890 --count 10 --type permanent")
        print("  python license_generator.py ABCDEF1234567890 --count 5 --type monthly --days 30")
        print("  python license_generator.py ABCDEF1234567890 --verify 'sig_b64.t_enc_b64'")
        return
    
    device_code = sys.argv[1].upper().strip()
    
    # 解析参数
    count = 100
    license_type = "permanent"
    expiry_days = None
    key_path = "license_priv_new.pem"
    output_file = None
    verify_blob = None
    
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--count" and i + 1 < len(sys.argv):
            count = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--type" and i + 1 < len(sys.argv):
            license_type = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--days" and i + 1 < len(sys.argv):
            expiry_days = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--key" and i + 1 < len(sys.argv):
            key_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--verify" and i + 1 < len(sys.argv):
            verify_blob = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    
    # 验证模式
    if verify_blob:
        private_key = load_private_key(key_path)
        public_key = private_key.public_key()
        valid, info = verify_license_blob(verify_blob, device_code, public_key)
        print(f"验证结果: {'通过' if valid else '失败'}")
        for k, v in info.items():
            print(f"  {k}: {v}")
        return
    
    # 检查私钥文件
    if not os.path.exists(key_path):
        print(f"错误: 私钥文件不存在: {key_path}")
        print("请先生成密钥对或指定正确的 --key 路径")
        return
    
    # 设置月卡过期天数
    if license_type == "monthly" and expiry_days is None:
        expiry_days = 30
    
    # 批量生成
    licenses = batch_generate(device_code, key_path, count, license_type, expiry_days)
    
    # 导出 CSV
    if output_file:
        export_licenses_csv(licenses, output_file, device_code, license_type, expiry_days)

if __name__ == "__main__":
    main()