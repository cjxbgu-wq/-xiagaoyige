#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VCam 卡密生成系统 - Tkinter 图形界面
双击启动，调出界面，无需额外安装依赖
"""

import sys
import os
import hashlib
import base64
import struct
import csv
import threading
from datetime import datetime
from tkinter import (
    Tk, Frame, Label, Entry, Button, Spinbox,
    filedialog, messagebox, scrolledtext, Menu,
    StringVar, IntVar, Toplevel
)
from tkinter import ttk
from tkinter.font import Font

# 导入核心生成逻辑
from license_generator import (
    load_private_key, public_key_to_x962_hex,
    generate_license_blob, verify_license_blob,
    DEFAULT_T_TRUE, T_SALT_HEX, MAGIC_VALUE
)

class LicenseGeneratorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VCam 卡密生成系统 v1.0")
        self.root.geometry("1000x700")
        self.root.minsize(900, 600)
        
        self.private_key = None
        self.public_key = None
        self.licenses = []
        self.worker_thread = None
        
        # 设置字体
        self.default_font = Font(family="Microsoft YaHei", size=9)
        self.mono_font = Font(family="Consolas", size=8)
        self.root.option_add("*Font", self.default_font)
        
        self.create_widgets()
        self.load_default_key()
    
    def create_widgets(self):
        # 主布局
        main_frame = Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # ===== 密钥信息区 =====
        key_frame = ttk.LabelFrame(main_frame, text="密钥信息", padding=10)
        key_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(key_frame, text="私钥路径:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.key_path_var = StringVar()
        self.key_path_entry = ttk.Entry(key_frame, textvariable=self.key_path_var, width=80, state="readonly")
        self.key_path_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Button(key_frame, text="浏览...", command=self.browse_key).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(key_frame, text="公钥:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.pub_key_var = StringVar(value="未加载")
        self.pub_key_entry = ttk.Entry(key_frame, textvariable=self.pub_key_var, width=80, state="readonly", font=self.mono_font)
        self.pub_key_entry.grid(row=1, column=1, columnspan=2, sticky="ew", padx=5, pady=5)
        
        key_frame.columnconfigure(1, weight=1)
        
        # ===== 生成参数区 =====
        param_frame = ttk.LabelFrame(main_frame, text="生成参数", padding=10)
        param_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(param_frame, text="设备码 *:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.device_code_var = StringVar()
        self.device_code_entry = ttk.Entry(param_frame, textvariable=self.device_code_var, width=40)
        self.device_code_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.device_code_entry.bind("<KeyRelease>", self.on_device_code_changed)
        
        ttk.Label(param_frame, text="卡密类型:").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.type_var = StringVar(value="永久卡")
        self.type_combo = ttk.Combobox(param_frame, textvariable=self.type_var, values=["永久卡", "月卡"], state="readonly", width=15)
        self.type_combo.grid(row=0, column=3, sticky="w", padx=5, pady=5)
        self.type_combo.bind("<<ComboboxSelected>>", self.on_type_changed)
        
        ttk.Label(param_frame, text="有效天数:").grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.days_var = IntVar(value=30)
        self.days_spin = Spinbox(param_frame, from_=1, to=3650, textvariable=self.days_var, width=10)
        self.days_spin.grid(row=1, column=3, sticky="w", padx=5, pady=5)
        
        ttk.Label(param_frame, text="生成数量:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.count_var = IntVar(value=100)
        self.count_spin = Spinbox(param_frame, from_=1, to=10000, textvariable=self.count_var, width=15)
        self.count_spin.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        param_frame.columnconfigure(1, weight=1)
        
        # ===== 操作按钮区 =====
        btn_frame = Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        self.generate_btn = Button(btn_frame, text="生成卡密", command=self.start_generate, 
                                   height=2, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 10, "bold"))
        self.generate_btn.pack(side="left", padx=5, fill="x", expand=True)
        
        self.verify_btn = Button(btn_frame, text="验证单个卡密", command=self.verify_single,
                                 height=2, bg="#2196F3", fg="white")
        self.verify_btn.pack(side="left", padx=5, fill="x", expand=True)
        
        self.export_btn = Button(btn_frame, text="导出 CSV", command=self.export_csv,
                                 height=2, bg="#FF9800", fg="white", state="disabled")
        self.export_btn.pack(side="left", padx=5, fill="x", expand=True)
        
        self.clear_btn = Button(btn_frame, text="清空列表", command=self.clear_table,
                                height=2, bg="#f44336", fg="white")
        self.clear_btn.pack(side="left", padx=5, fill="x", expand=True)
        
        # ===== 进度条 =====
        self.progress_var = IntVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_bar.pack_forget()  # 初始隐藏
        
        # ===== 结果表格区 =====
        table_frame = ttk.LabelFrame(main_frame, text="生成结果", padding=5)
        table_frame.pack(fill="both", expand=True)
        
        # 创建 Treeview
        columns = ("index", "blob", "type", "expiry", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("index", text="序号")
        self.tree.heading("blob", text="卡密")
        self.tree.heading("type", text="类型")
        self.tree.heading("expiry", text="有效期")
        self.tree.heading("status", text="状态")
        
        self.tree.column("index", width=50, anchor="center")
        self.tree.column("blob", width=500)
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("expiry", width=80, anchor="center")
        self.tree.column("status", width=60, anchor="center")
        
        # 滚动条
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        
        # 双击复制
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # 右键菜单
        self.create_context_menu()
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        # 底部提示
        hint_label = Label(main_frame, text="提示: 双击行可复制卡密 | 右键菜单提供更多操作", 
                          fg="gray", font=("Microsoft YaHei", 8))
        hint_label.pack(pady=(5, 0))
        
        # 状态栏
        self.status_var = StringVar(value="就绪")
        self.status_label = Label(self.root, textvariable=self.status_var, 
                                  bd=1, relief="sunken", anchor="w")
        self.status_label.pack(fill="x", side="bottom", padx=10, pady=5)
    
    def create_context_menu(self):
        self.context_menu = Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="复制卡密", command=self.copy_selected)
        self.context_menu.add_command(label="复制完整卡密", command=self.copy_full_blob)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="验证此卡密", command=self.verify_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="删除此行", command=self.delete_selected)
    
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
    
    def load_default_key(self):
        default_paths = [
            "license_priv_new.pem",
            "license_priv.pem",
            "../license_priv.pem",
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                self.load_key(path)
                break
    
    def browse_key(self):
        path = filedialog.askopenfilename(
            title="选择私钥文件",
            filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")]
        )
        if path:
            self.load_key(path)
    
    def load_key(self, path):
        try:
            self.private_key = load_private_key(path)
            self.public_key = self.private_key.public_key()
            
            self.key_path_var.set(os.path.abspath(path))
            
            pub_hex = public_key_to_x962_hex(self.public_key)
            self.pub_key_var.set(pub_hex)
            
            self.status_var.set(f"已加载私钥: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"加载私钥失败:\n{str(e)}")
    
    def on_device_code_changed(self, event):
        text = self.device_code_var.get().upper()
        filtered = ''.join(c for c in text if c in '0123456789ABCDEF')
        if filtered != text:
            self.device_code_var.set(filtered)
    
    def on_type_changed(self, event):
        if self.type_var.get() == "月卡":
            self.days_spin.config(state="normal")
        else:
            self.days_spin.config(state="disabled")
    
    def validate_inputs(self):
        device_code = self.device_code_var.get().strip()
        if len(device_code) != 16:
            messagebox.showwarning("错误", "设备码必须是 16 位十六进制字符")
            return False
        
        if self.private_key is None:
            messagebox.showwarning("错误", "请先加载私钥文件")
            return False
        
        return True
    
    def start_generate(self):
        if not self.validate_inputs():
            return
        
        device_code = self.device_code_var.get().strip()
        count = self.count_var.get()
        license_type = "monthly" if self.type_var.get() == "月卡" else "permanent"
        expiry_days = self.days_var.get() if license_type == "monthly" else None
        
        self.generate_btn.config(state="disabled")
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_var.set(0)
        self.progress_bar.config(maximum=count)
        self.status_var.set("正在生成...")
        
        self.worker_thread = threading.Thread(
            target=self.generate_worker,
            args=(device_code, self.private_key, count, license_type, expiry_days),
            daemon=True
        )
        self.worker_thread.start()
        
        # 定时检查进度
        self.root.after(100, self.check_worker_progress)
    
    def generate_worker(self, device_code, private_key, count, license_type, expiry_days):
        try:
            public_key = private_key.public_key()
            licenses = []
            
            for i in range(count):
                t_custom = DEFAULT_T_TRUE.copy()
                t_custom[1] = (t_custom[1] + i) & 0xFFFFFFFF
                
                blob = generate_license_blob(
                    device_code, private_key, 
                    t_custom, expiry_days
                )
                
                valid, info = verify_license_blob(blob, device_code, public_key)
                
                licenses.append({
                    "index": i + 1,
                    "blob": blob,
                    "valid": valid,
                    "info": info,
                    "type": license_type,
                    "expiry_days": expiry_days
                })
                
                # 更新进度（线程安全方式）
                self.root.after(0, lambda c=i+1: self.progress_var.set(c))
            
            # 完成回调
            self.root.after(0, lambda: self.on_generate_finished(licenses))
            
        except Exception as e:
            self.root.after(0, lambda: self.on_generate_error(str(e)))
    
    def check_worker_progress(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.root.after(100, self.check_worker_progress)
    
    def on_generate_finished(self, licenses):
        self.licenses = licenses
        self.update_table()
        self.export_btn.config(state="normal")
        self.generate_btn.config(state="normal")
        self.progress_bar.pack_forget()
        
        valid_count = sum(1 for l in licenses if l["valid"])
        self.status_var.set(f"生成完成: {valid_count}/{len(licenses)} 个验证通过")
    
    def on_generate_error(self, error_msg):
        self.generate_btn.config(state="normal")
        self.progress_bar.pack_forget()
        messagebox.showerror("错误", f"生成失败:\n{error_msg}")
        self.status_var.set("生成失败")
    
    def update_table(self):
        # 清空现有数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 添加新数据
        for lic in self.licenses:
            blob_display = lic["blob"][:80] + "..." if len(lic["blob"]) > 80 else lic["blob"]
            type_text = "永久卡" if lic["type"] == "permanent" else "月卡"
            expiry_text = f"{lic['expiry_days']} 天" if lic["type"] == "monthly" else "永久"
            status_text = "有效" if lic["valid"] else "无效"
            
            item = self.tree.insert("", "end", values=(
                lic["index"], blob_display, type_text, expiry_text, status_text
            ), tags=("valid" if lic["valid"] else "invalid",))
        
        # 设置标签颜色
        self.tree.tag_configure("valid", foreground="green")
        self.tree.tag_configure("invalid", foreground="red")
    
    def verify_single(self):
        if self.private_key is None:
            messagebox.showwarning("错误", "请先加载私钥文件")
            return
        
        device_code = self.device_code_var.get().strip()
        if len(device_code) != 16:
            messagebox.showwarning("错误", "请输入正确的设备码")
            return
        
        # 创建验证对话框
        dialog = Toplevel(self.root)
        dialog.title("验证卡密")
        dialog.geometry("500x300")
        dialog.transient(self.root)
        dialog.grab_set()
        
        Label(dialog, text="请输入要验证的卡密:").pack(pady=10)
        
        text_area = scrolledtext.ScrolledText(dialog, width=60, height=8)
        text_area.pack(padx=10, pady=5, fill="both", expand=True)
        
        def do_verify():
            blob = text_area.get("1.0", "end").strip()
            if not blob:
                return
            public_key = self.private_key.public_key()
            valid, info = verify_license_blob(blob, device_code, public_key)
            
            result_text = "验证通过！\n\n" if valid else f"验证失败: {info.get('error', '未知错误')}\n\n"
            for k, v in info.items():
                result_text += f"{k}: {v}\n"
            
            result_area.config(state="normal")
            result_area.delete("1.0", "end")
            result_area.insert("1.0", result_text)
            result_area.config(state="disabled")
        
        Button(dialog, text="验证", command=do_verify, bg="#2196F3", fg="white").pack(pady=5)
        
        Label(dialog, text="验证结果:").pack()
        result_area = scrolledtext.ScrolledText(dialog, width=60, height=8, state="disabled")
        result_area.pack(padx=10, pady=5, fill="both", expand=True)
        
        Button(dialog, text="关闭", command=dialog.destroy).pack(pady=10)
    
    def export_csv(self):
        if not self.licenses:
            return
        
        path = filedialog.asksaveasfilename(
            title="导出 CSV",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            initialfile="licenses.csv"
        )
        if path:
            try:
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["序号", "卡密", "类型", "有效天数", "设备码", "生成时间", "验证状态"])
                    for lic in self.licenses:
                        writer.writerow([
                            lic["index"],
                            lic["blob"],
                            "永久卡" if lic["type"] == "permanent" else "月卡",
                            lic["expiry_days"] if lic["type"] == "monthly" else "永久",
                            self.device_code_var.get().strip(),
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "有效" if lic["valid"] else "无效"
                        ])
                messagebox.showinfo("成功", f"已导出到:\n{path}")
                self.status_var.set(f"已导出: {path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败:\n{str(e)}")
    
    def clear_table(self):
        self.licenses = []
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.export_btn.config(state="disabled")
        self.status_var.set("已清空")
    
    def on_double_click(self, event):
        self.copy_selected()
    
    def copy_selected(self):
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            row_idx = self.tree.index(item)
            if 0 <= row_idx < len(self.licenses):
                blob = self.licenses[row_idx]["blob"]
                self.root.clipboard_clear()
                self.root.clipboard_append(blob)
                self.status_var.set(f"已复制第 {row_idx+1} 个卡密")
    
    def copy_full_blob(self):
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            row_idx = self.tree.index(item)
            if 0 <= row_idx < len(self.licenses):
                blob = self.licenses[row_idx]["blob"]
                self.root.clipboard_clear()
                self.root.clipboard_append(blob)
                self.status_var.set(f"已复制完整卡密 (第 {row_idx+1} 个)")
    
    def verify_selected(self):
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            row_idx = self.tree.index(item)
            if 0 <= row_idx < len(self.licenses):
                lic = self.licenses[row_idx]
                device_code = self.device_code_var.get().strip()
                public_key = self.private_key.public_key()
                valid, info = verify_license_blob(lic["blob"], device_code, public_key)
                
                if valid:
                    msg = "验证通过！\n\n"
                else:
                    msg = f"验证失败: {info.get('error', '未知错误')}\n\n"
                for k, v in info.items():
                    msg += f"{k}: {v}\n"
                messagebox.showinfo("验证结果", msg)
    
    def delete_selected(self):
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            row_idx = self.tree.index(item)
            if 0 <= row_idx < len(self.licenses):
                self.licenses.pop(row_idx)
                self.update_table()
                if not self.licenses:
                    self.export_btn.config(state="disabled")
                self.status_var.set(f"已删除第 {row_idx+1} 个卡密")


def main():
    root = Tk()
    app = LicenseGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()