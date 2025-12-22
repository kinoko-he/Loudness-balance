# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import customtkinter as ctk
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import datetime
import json
import configparser
import re
from tkinterdnd2 import TkinterDnD, DND_FILES

# 设置控制台编码为UTF-8 (Windows兼容性)
if os.name == 'nt':  # Windows系统
    try:
        # 尝试设置控制台编码
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# 设置CustomTkinter主题
ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

class TranscoderApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        
        # 初始化文件对话框活动标志
        self._file_dialog_active = False
        
        # 配置窗口
        self.title("音视频快速转码工具")
        self.geometry("1200x800")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # 检查FFmpeg是否可用
        self.ffmpeg_available = self.check_ffmpeg()
        if not self.ffmpeg_available:
            messagebox.showerror("错误", "未找到FFmpeg，请确保FFmpeg已安装并添加到系统PATH中。")
            sys.exit(1)
            
        # 检查GPU支持
        self.gpu_supported = self.check_gpu_support()
        
        # 响度平衡相关变量
        self.loudness_enabled = tk.BooleanVar(value=True)  # 默认启用响度平衡
        self.target_lufs = tk.DoubleVar(value=-13.0)  # 目标响度，默认-13 LUFS
        self.max_true_peak = tk.DoubleVar(value=-1.0)  # 最大真峰值，默认-1.0 dB
        self.loudness_range = tk.DoubleVar(value=7.0)  # 响度范围，默认7 LU
        
        # 新增专业音频设置
        self.audio_bitrate = tk.StringVar(value="192k")
        self.sample_rate = tk.StringVar(value="48000")
        self.audio_channels = tk.StringVar(value="2")
        self.enable_eq = tk.BooleanVar(value=False)  # 人声清晰度增强EQ
        
        # 配置拖放
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.drop_files)
        
        # 加载配置
        self.load_loudness_config()
        
        # 创建UI
        self.create_widgets()
        
    def check_ffmpeg(self):
        """检查FFmpeg是否已安装"""
        try:
            # 在Windows上使用CREATE_NO_WINDOW标志避免显示控制台窗口
            if os.name == 'nt':
                subprocess.run(
                    ["ffmpeg", "-version"], 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.run(
                    ["ffmpeg", "-version"], 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )
            return True
        except FileNotFoundError:
            return False
            
    def check_gpu_support(self):
        """检查GPU加速支持"""
        try:
            # 检查NVIDIA GPU支持
            if os.name == 'nt':
                result = subprocess.run(
                    ["ffmpeg", "-h", "encoder=h264_nvenc"], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                result = subprocess.run(
                    ["ffmpeg", "-h", "encoder=h264_nvenc"], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )
            return result.returncode == 0
        except:
            return False
            
    def create_widgets(self):
        """创建UI控件"""
        # 创建顶部框架
        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(7, weight=1)
        
        # 添加文件按钮
        add_files_btn = ctk.CTkButton(top_frame, text="添加文件", command=self.add_files)
        add_files_btn.grid(row=0, column=0, padx=5, pady=5)
        
        # 添加文件夹按钮
        add_folder_btn = ctk.CTkButton(top_frame, text="添加文件夹", command=self.add_folder)
        add_folder_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # 开始转码按钮
        start_btn = ctk.CTkButton(top_frame, text="开始转码", command=self.start_transcoding)
        start_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # 响度平衡按钮
        loudness_btn = ctk.CTkButton(top_frame, text="响度平衡", command=self.start_loudness_normalization)
        loudness_btn.grid(row=0, column=3, padx=5, pady=5)
        
        # 清空列表按钮
        clear_btn = ctk.CTkButton(top_frame, text="清空列表", command=self.clear_list)
        clear_btn.grid(row=0, column=4, padx=5, pady=5)
        
        # GPU加速开关
        self.gpu_var = tk.BooleanVar(value=self.gpu_supported)
        gpu_check = ctk.CTkCheckBox(top_frame, text="启用GPU加速", variable=self.gpu_var, state="normal" if self.gpu_supported else "disabled")
        gpu_check.grid(row=0, column=5, padx=5, pady=5, sticky="w")
        
        # 覆盖源文件开关
        self.overwrite_var = tk.BooleanVar(value=True)  # 默认开启
        overwrite_check = ctk.CTkCheckBox(top_frame, text="覆盖源文件", variable=self.overwrite_var)
        overwrite_check.grid(row=0, column=6, padx=5, pady=5, sticky="w")
        
        # 响度平衡设置按钮
        loudness_settings_btn = ctk.CTkButton(top_frame, text="响度设置", command=self.show_loudness_settings)
        loudness_settings_btn.grid(row=0, column=7, padx=5, pady=5, sticky="e")
        
        # 创建主内容区域
        content_frame = ctk.CTkFrame(self)
        content_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=2)  # 文件列表占更多空间
        content_frame.grid_columnconfigure(1, weight=1)  # 日志区域
        content_frame.grid_rowconfigure(0, weight=1)
        
        # 左侧：文件列表框架
        list_frame = ctk.CTkFrame(content_frame)
        list_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # 创建Treeview来显示文件列表
        self.tree = ttk.Treeview(list_frame, columns=("path", "status"), show="tree headings")
        self.tree.heading("#0", text="文件名")
        self.tree.heading("path", text="完整路径")
        self.tree.heading("status", text="状态")
        self.tree.column("#0", width=200)
        self.tree.column("path", width=400)
        self.tree.column("status", width=100)
        
        # 设置Treeview样式
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))
        
        # 添加滚动条
        tree_scroll_y = ctk.CTkScrollbar(list_frame, orientation="vertical", command=self.tree.yview)
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll_y.set)
        
        tree_scroll_x = ctk.CTkScrollbar(list_frame, orientation="horizontal", command=self.tree.xview)
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        self.tree.configure(xscrollcommand=tree_scroll_x.set)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        
        # 右侧：日志区域
        log_frame = ctk.CTkFrame(content_frame)
        log_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        
        # 日志标题
        log_label = ctk.CTkLabel(log_frame, text="转码日志", font=ctk.CTkFont(size=16, weight="bold"))
        log_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=20, width=40, 
                                                 font=('Consolas', 9))
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        # 清空日志按钮
        clear_log_btn = ctk.CTkButton(log_frame, text="清空日志", command=self.clear_log)
        clear_log_btn.grid(row=2, column=0, padx=10, pady=5)
        
        # 移除拖拽事件绑定，避免误触发文件加载
        
        # 初始化日志
        self.log_message("程序启动完成")
        self.log_message(f"FFmpeg状态: {'可用' if self.ffmpeg_available else '不可用'}")
        self.log_message(f"GPU加速: {'支持' if self.gpu_supported else '不支持'}")
        
        # 显示当前响度平衡参数
        self.log_message("=== 当前响度平衡参数 ===")
        self.log_message(f"目标响度: {self.target_lufs.get()} LUFS")
        self.log_message(f"最大真峰值: {self.max_true_peak.get()} dB")
        self.log_message(f"响度范围: {self.loudness_range.get()} LU")
        self.log_message(f"音质增强(EQ): {self.enable_eq.get()}")
        self.log_message("========================")
        
        # 创建进度条
        self.progress_bar = ctk.CTkProgressBar(self, mode="determinate")
        self.progress_bar.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)
        
        # 创建状态栏
        self.status_var = tk.StringVar(value="就绪 (支持文件拖放)")
        status_bar = ctk.CTkLabel(self, textvariable=self.status_var, anchor="w")
        status_bar.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        
    def drop_files(self, event):
        """处理文件拖放"""
        try:
            files = self.tk.splitlist(event.data)
            count = 0
            for f in files:
                if os.path.exists(f):
                    # 检查是否是文件夹
                    if os.path.isdir(f):
                        for root, dirs, filenames in os.walk(f):
                            for filename in filenames:
                                if filename.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
                                                        '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a')):
                                    self.add_file_to_list(os.path.join(root, filename))
                                    count += 1
                    else:
                        # 检查文件扩展名
                        if f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
                                            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a')):
                            self.add_file_to_list(f)
                            count += 1
            if count > 0:
                self.log_message(f"通过拖放添加了 {count} 个文件")
        except Exception as e:
            self.log_message(f"拖放文件处理出错: {e}")
        
    def show_loudness_settings(self):
        """显示响度平衡设置对话框"""
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("响度平衡设置")
        settings_window.geometry("600x650")
        settings_window.resizable(True, True)
        settings_window.grab_set()
        
        # 创建滚动框架
        scroll_frame = ctk.CTkScrollableFrame(settings_window)
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 说明文本
        info_label = ctk.CTkLabel(scroll_frame, text="当前模式: 自动动态均衡 + 目标响度标准化\n(自动解决声音忽大忽小问题，并统一音量标准)", 
                                 font=("Arial", 14), text_color="gray")
        info_label.pack(fill="x", padx=10, pady=10)
        
        # 1. 增强选项
        enhance_frame = ctk.CTkFrame(scroll_frame)
        enhance_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(enhance_frame, text="音质增强", font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        eq_check = ctk.CTkCheckBox(enhance_frame, text="启用人声清晰度增强 (EQ)", variable=self.enable_eq)
        eq_check.pack(anchor="w", padx=20, pady=10)
        
        ctk.CTkLabel(enhance_frame, text="优化频率响应，消除低频噪音，提升人声清晰度。\n适合对话和短剧。", 
                    text_color="gray", justify="left", font=("Arial", 12)).pack(anchor="w", padx=45, pady=0)
        
        # 2. 响度参数
        loudnorm_frame = ctk.CTkFrame(scroll_frame)
        loudnorm_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(loudnorm_frame, text="响度参数 (标准)", font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        # 目标响度
        ln_grid = ctk.CTkFrame(loudnorm_frame, fg_color="transparent")
        ln_grid.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(ln_grid, text="目标响度 (LUFS):").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        target_entry = ctk.CTkEntry(ln_grid, width=100)
        target_entry.insert(0, str(self.target_lufs.get()))
        target_entry.grid(row=0, column=1, padx=10, pady=5)
        ctk.CTkLabel(ln_grid, text="(-30 ~ 5)", text_color="gray").grid(row=0, column=2, padx=5, pady=5)
        
        # 最大真峰值
        ctk.CTkLabel(ln_grid, text="最大真峰值 (dB):").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        peak_entry = ctk.CTkEntry(ln_grid, width=100)
        peak_entry.insert(0, str(self.max_true_peak.get()))
        peak_entry.grid(row=1, column=1, padx=10, pady=5)
        ctk.CTkLabel(ln_grid, text="(-6 ~ -0.1)", text_color="gray").grid(row=1, column=2, padx=5, pady=5)
        
        # 响度范围
        ctk.CTkLabel(ln_grid, text="响度范围 (LU):").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        range_entry = ctk.CTkEntry(ln_grid, width=100)
        range_entry.insert(0, str(self.loudness_range.get()))
        range_entry.grid(row=2, column=1, padx=10, pady=5)
        ctk.CTkLabel(ln_grid, text="(1 ~ 20)", text_color="gray").grid(row=2, column=2, padx=5, pady=5)
        
        # 3. 音频输出设置
        audio_frame = ctk.CTkFrame(scroll_frame)
        audio_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(audio_frame, text="音频输出设置", font=("Arial", 16, "bold")).pack(anchor="w", padx=10, pady=5)
        
        af_grid = ctk.CTkFrame(audio_frame, fg_color="transparent")
        af_grid.pack(fill="x", padx=10, pady=5)
        
        # 码率
        ctk.CTkLabel(af_grid, text="音频码率:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        bitrate_combo = ctk.CTkComboBox(af_grid, values=['128k', '192k', '256k', '320k'], variable=self.audio_bitrate)
        bitrate_combo.grid(row=0, column=1, padx=10, pady=10)
        
        # 采样率
        ctk.CTkLabel(af_grid, text="采样率:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        sample_combo = ctk.CTkComboBox(af_grid, values=['自动', '44100', '48000'], variable=self.sample_rate)
        sample_combo.grid(row=1, column=1, padx=10, pady=10)
        
        # 声道
        ctk.CTkLabel(af_grid, text="声道:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        channels_combo = ctk.CTkComboBox(af_grid, values=['自动', '立体声 (2.0)', '单声道'], variable=self.audio_channels)
        channels_combo.grid(row=2, column=1, padx=10, pady=10)
        
        # 按钮区域
        btn_frame = ctk.CTkFrame(settings_window, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=20)
        
        def save_settings():
            try:
                # 验证 EBU R128 参数
                target_val = float(target_entry.get())
                if not -30 <= target_val <= 5: raise ValueError("目标响度必须在-30到5之间")
                self.target_lufs.set(target_val)
                
                peak_val = float(peak_entry.get())
                if not -6 <= peak_val <= -0.1: raise ValueError("最大真峰值必须在-6到-0.1之间")
                self.max_true_peak.set(peak_val)
                
                range_val = float(range_entry.get())
                if not 1 <= range_val <= 20: raise ValueError("响度范围必须在1到20之间")
                self.loudness_range.set(range_val)
                
                # 保存配置
                self.save_loudness_config()
                settings_window.destroy()
                
            except ValueError as e:
                messagebox.showerror("参数错误", str(e))
        
        ctk.CTkButton(btn_frame, text="确定", command=save_settings, width=100).pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="取消", command=settings_window.destroy, width=100, fg_color="gray").pack(side="right", padx=10)
    
    def save_loudness_config(self):
        """保存响度平衡配置到文件"""
        try:
            config = configparser.ConfigParser()
            config['LOUDNESS'] = {
                'target_lufs': str(self.target_lufs.get()),
                'max_true_peak': str(self.max_true_peak.get()),
                'loudness_range': str(self.loudness_range.get()),
                'audio_bitrate': self.audio_bitrate.get(),
                'sample_rate': self.sample_rate.get(),
                'audio_channels': self.audio_channels.get(),
                'enable_eq': str(self.enable_eq.get())
            }

            
            config_path = os.path.join(os.path.dirname(__file__), 'loudness_config.ini')
            with open(config_path, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            
            self.log_message("响度平衡配置已保存")
        except Exception as e:
            self.log_message(f"保存配置失败: {str(e)}")
    
    def load_loudness_config(self):
        """从文件加载响度平衡配置"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'loudness_config.ini')
            if os.path.exists(config_path):
                config = configparser.ConfigParser()
                config.read(config_path, encoding='utf-8')
                
                if 'LOUDNESS' in config:
                    loudness_config = config['LOUDNESS']
                    target_lufs = float(loudness_config.get('target_lufs', -13.0))
                    max_true_peak = float(loudness_config.get('max_true_peak', -1.0))
                    loudness_range = float(loudness_config.get('loudness_range', 7.0))
                    audio_bitrate = loudness_config.get('audio_bitrate', '192k')
                    sample_rate = loudness_config.get('sample_rate', '48000')
                    audio_channels = loudness_config.get('audio_channels', '2')
                    enable_eq = loudness_config.get('enable_eq', 'False') == 'True'
                    
                    self.target_lufs.set(target_lufs)
                    self.max_true_peak.set(max_true_peak)
                    self.loudness_range.set(loudness_range)
                    self.audio_bitrate.set(audio_bitrate)
                    self.sample_rate.set(sample_rate)
                    self.audio_channels.set(audio_channels)
                    self.enable_eq.set(enable_eq)
                    
                    self.log_message("响度平衡配置已加载")
                    self.log_message(f"加载的参数: 目标响度={target_lufs} LUFS, 音质增强={enable_eq}")
                else:
                    self.log_message("配置文件中未找到 [LOUDNESS] 节，使用默认参数")
            else:
                self.log_message("配置文件不存在，使用默认参数")
        except Exception as e:
            self.log_message(f"加载配置失败: {str(e)}，使用默认参数")
        
    def log_message(self, message):
        """添加日志消息"""
        try:
            # 检查log_text是否存在
            if hasattr(self, 'log_text') and self.log_text is not None:
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                log_entry = f"[{timestamp}] {message}\n"
                self.log_text.insert(tk.END, log_entry)
                self.log_text.see(tk.END)
                self.update_idletasks()
            else:
                # 如果log_text不存在，直接打印到控制台
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}")
        except Exception as e:
            print(f"日志显示失败: {e}")
            
    def clear_log(self):
        """清空日志"""
        # 检查log_text是否存在
        if hasattr(self, 'log_text') and self.log_text is not None:
            self.log_text.delete(1.0, tk.END)
        self.log_message("日志已清空")
        
    # 以下函数已移除，不再支持拖拽功能
    # def on_click(self, event):
    #     pass
    # def on_drag(self, event):
    #     pass
    # def on_drop(self, event):
    #     pass
            
    def add_files(self):
        """添加文件到列表"""
        try:
            # 设置标志，表示正在执行文件选择对话框操作
            self._file_dialog_active = True
            
            files = filedialog.askopenfilenames(
                title="选择要转码的文件",
                filetypes=[
                    ("音视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.mp3 *.wav *.flac *.aac *.ogg *.m4a"),
                    ("所有文件", "*.*")
                ]
            )
            
            # 重置标志
            self._file_dialog_active = False
            
            if files:
                self.log_message(f"选择了 {len(files)} 个文件")
                for file in files:
                    self.add_file_to_list(file)
        except Exception as e:
            # 确保标志被重置
            self._file_dialog_active = False
            self.log_message(f"添加文件时出错: {e}")
            messagebox.showerror("错误", f"添加文件时出错: {e}")
            
    def add_folder(self):
        """添加整个文件夹的文件到列表"""
        try:
            # 设置标志，表示正在执行文件夹选择对话框操作
            self._file_dialog_active = True
            
            folder = filedialog.askdirectory(title="选择包含要转码文件的文件夹")
            
            # 重置标志
            self._file_dialog_active = False
            
            if folder:
                self.log_message(f"选择文件夹: {folder}")
                file_count = 0
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        if file.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
                                                '.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a')):
                            self.add_file_to_list(os.path.join(root, file))
                            file_count += 1
                self.log_message(f"从文件夹添加了 {file_count} 个文件")
        except Exception as e:
            # 确保标志被重置
            self._file_dialog_active = False
            self.log_message(f"添加文件夹时出错: {e}")
            messagebox.showerror("错误", f"添加文件夹时出错: {e}")
                        
    def clear_list(self):
        """清空文件列表"""
        item_count = len(self.tree.get_children())
        for item in self.tree.get_children():
            self.tree.delete(item)
        if item_count > 0:
            self.log_message(f"清空了 {item_count} 个文件")
                        
    def add_file_to_list(self, file_path):
        """将文件添加到列表中"""
        # 检查文件是否已存在
        for child in self.tree.get_children():
            if self.tree.item(child, "values")[0] == file_path:
                self.log_message(f"文件已存在，跳过: {os.path.basename(file_path)}")
                return  # 文件已存在，不重复添加
                
        # 添加文件到列表
        filename = os.path.basename(file_path)
        self.tree.insert("", "end", text=filename, values=(file_path, "等待中"))
        self.log_message(f"添加文件: {filename}")
        
    def start_transcoding(self):
        """开始转码"""
        try:
            # 获取所有文件
            files = []
            for child in self.tree.get_children():
                files.append(self.tree.item(child, "values")[0])
                
            if not files:
                self.log_message("没有文件需要转码")
                messagebox.showwarning("警告", "请先添加要转码的文件")
                return
                
            self.log_message(f"准备转码 {len(files)} 个文件")
            
            # 确认是否覆盖源文件
            if self.overwrite_var.get():
                result = messagebox.askyesno("确认覆盖", "您已选择覆盖源文件，这将永久删除原始文件。是否继续？")
                if not result:
                    self.log_message("用户取消了覆盖操作")
                    return
                    
            # 在后台线程中执行转码
            self.log_message("开始转码任务")
            threading.Thread(target=self.transcode_files, args=(files,), daemon=True).start()
        except Exception as e:
            error_msg = f"启动转码时出错: {e}"
            self.log_message(error_msg)
            messagebox.showerror("错误", error_msg)
        
    def transcode_files(self, files):
        """执行文件转码"""
        try:
            total_files = len(files)
            completed_files = 0
            
            self.status_var.set(f"正在转码... (0/{total_files})")
            self.progress_bar.set(0)
            self.after(0, self.log_message, f"开始批量转码，共 {total_files} 个文件")
            
            # 改为单线程顺序处理，避免并发问题
            for i, file in enumerate(files):
                try:
                    self.after(0, self.log_message, f"开始处理文件 {i+1}/{total_files}: {os.path.basename(file)}")
                    result = self.transcode_single_file(file)
                    # 更新UI状态需要在主线程中执行
                    self.after(0, self.update_file_status, file, result)
                    self.after(0, self.log_message, f"文件转码完成: {os.path.basename(file)} - {result}")
                except Exception as e:
                    error_result = f"错误: {str(e)}"
                    self.after(0, self.update_file_status, file, error_result)
                    self.after(0, self.log_message, f"文件转码失败: {os.path.basename(file)} - {error_result}")
                
                # 更新进度
                completed_files += 1
                progress = completed_files / total_files
                self.progress_bar.set(progress)
                self.status_var.set(f"正在转码... ({completed_files}/{total_files})")
                    
            self.status_var.set("转码完成")
            self.progress_bar.set(1.0)
            self.after(0, self.log_message, "所有文件转码完成")
            
            # 显示完成消息
            self.after(0, lambda: messagebox.showinfo("完成", f"已完成转码 {total_files} 个文件"))
        except Exception as e:
            error_msg = f"批量转码过程出错: {e}"
            self.after(0, self.log_message, error_msg)
            self.after(0, lambda: messagebox.showerror("错误", error_msg))
        
    def transcode_single_file(self, file_path):
        """转码单个文件"""
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return f"失败: 文件不存在"
            
            # 获取文件信息
            file_dir = os.path.dirname(file_path)
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            file_ext = os.path.splitext(file_path)[1]
            
            # 确保输出目录存在
            if not os.path.exists(file_dir):
                return f"失败: 输出目录不存在"
            
            # 检查文件类型
            if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm')):
                # 视频文件
                if self.overwrite_var.get():
                    # 覆盖源文件，先转码为临时文件
                    output_path = os.path.join(file_dir, f"{file_name}_temp.mp4")
                else:
                    # 不覆盖源文件，添加_transcoded后缀
                    output_path = os.path.join(file_dir, f"{file_name}_transcoded.mp4")
                    
                # 构建FFmpeg命令
                cmd = [
                    "ffmpeg",
                    "-i", file_path,  # 输入文件
                ]
                
                # 根据GPU支持情况选择编码器
                if self.gpu_var.get() and self.gpu_supported:
                    cmd.extend(["-c:v", "h264_nvenc"])  # NVIDIA GPU编码器
                else:
                    cmd.extend(["-c:v", "libx264"])  # CPU编码器
                    
                cmd.extend([
                    "-preset", "fast",  # 编码速度
                    "-crf", "23",  # 视频质量
                    "-c:a", "aac",  # 音频编码器
                    "-b:a", "128k",  # 音频码率
                    "-y",  # 覆盖输出文件
                    output_path
                ])
            else:
                # 音频文件 - 转换成AAC格式（128k码率）
                if self.overwrite_var.get():
                    # 覆盖源文件，先转码为临时文件
                    output_path = os.path.join(file_dir, f"{file_name}_temp.aac")
                else:
                    # 不覆盖源文件，添加_transcoded后缀
                    output_path = os.path.join(file_dir, f"{file_name}_transcoded.aac")
                
                # 构建FFmpeg命令 - 转换为AAC格式（128k码率，保持原始时长）
                cmd = [
                    "ffmpeg",
                    "-i", file_path,  # 输入文件
                    "-vn",  # 不要视频流
                    "-map", "0:a:0",  # 明确映射第一个音频流
                    "-avoid_negative_ts", "make_zero",  # 避免负时间戳
                    "-fflags", "+genpts",  # 重新生成时间戳
                    "-acodec", "aac",  # AAC编码器
                    "-b:a", "128k",  # 128k码率
                    "-map_metadata", "0",  # 保留所有元数据
                    "-y",  # 覆盖输出文件
                    output_path
                ]
            
            # 检查输出文件路径是否有效
            try:
                # 尝试创建输出文件来测试路径
                with open(output_path, 'w') as test_file:
                    pass
                os.remove(output_path)  # 删除测试文件
            except Exception as e:
                return f"失败: 输出路径无效 - {str(e)}"
                
            # 执行FFmpeg命令，使用更安全的方式
            try:
                if os.name == 'nt':
                    # Windows系统，使用更保守的设置
                    result = subprocess.run(
                        cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=False,  # 使用字节模式避免编码问题
                        timeout=300,  # 5分钟超时
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    # 手动解码输出
                    try:
                        stdout_text = result.stdout.decode('utf-8', errors='ignore')
                        stderr_text = result.stderr.decode('utf-8', errors='ignore')
                    except:
                        stdout_text = str(result.stdout)
                        stderr_text = str(result.stderr)
                else:
                    result = subprocess.run(
                        cmd, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True, 
                        encoding='utf-8',
                        errors='ignore',
                        timeout=300
                    )
                    stdout_text = result.stdout
                    stderr_text = result.stderr
            except subprocess.TimeoutExpired:
                return f"失败: 转码超时（超过5分钟）"
            except Exception as e:
                return f"失败: 执行FFmpeg时出错 - {str(e)}"
            
            # 如果转码成功且需要覆盖源文件，则替换源文件
            if result.returncode == 0:
                # 验证输出文件是否存在且有效
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    return "失败: 输出文件无效或为空"
                
                # 可选：验证时长是否匹配（需要额外的FFmpeg调用）
                try:
                    # 获取原文件时长
                    duration_cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", file_path]
                    original_duration = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=30)
                    
                    # 获取输出文件时长
                    output_duration = subprocess.run(
                        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", output_path], 
                        capture_output=True, text=True, timeout=30
                    )
                    
                    if (original_duration.returncode == 0 and output_duration.returncode == 0 and 
                        original_duration.stdout.strip() and output_duration.stdout.strip()):
                        orig_dur = float(original_duration.stdout.strip())
                        out_dur = float(output_duration.stdout.strip())
                        duration_diff = abs(orig_dur - out_dur)
                        
                        # 如果时长差异超过1秒，记录警告
                        if duration_diff > 1.0:
                            self.after(0, self.log_message, f"警告: 时长差异 {duration_diff:.2f}秒 (原:{orig_dur:.2f}s -> 新:{out_dur:.2f}s)")
                except Exception:
                    # 时长验证失败不影响主流程
                    pass
                
                if self.overwrite_var.get():
                    try:
                        # 删除原始文件
                        os.remove(file_path)
                        # 重命名临时文件为原始文件名
                        if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm')):
                            new_output_path = os.path.join(file_dir, f"{file_name}{file_ext}")
                        else:
                            # 音频文件改为.aac扩展名
                            new_output_path = os.path.join(file_dir, f"{file_name}.aac")
                        os.rename(output_path, new_output_path)
                        return "完成 (已覆盖源文件)"
                    except Exception as e:
                        return f"完成 (替换文件时出错: {str(e)})"
                else:
                    return "完成"
            else:
                # 删除临时文件（如果存在）
                if os.path.exists(output_path):
                    os.remove(output_path)
                
                # 提取关键错误信息
                error_msg = f"FFmpeg失败 (返回码: {result.returncode})"
                if stderr_text:
                    # 提取关键错误信息
                    error_lines = stderr_text.split('\n')
                    key_errors = [line for line in error_lines if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable'])]
                    if key_errors:
                        error_msg += f" - {'; '.join(key_errors[:2])}"  # 只显示前2个关键错误
                    else:
                        error_msg += f" - {stderr_text[:100]}"  # 如果没有关键错误，显示前100字符
                return f"失败: {error_msg}"
                
        except Exception as e:
            return f"错误: {str(e)}"
            
    def start_loudness_normalization(self):
        """开始响度平衡处理"""
        try:
            # 获取所有文件
            files = []
            for child in self.tree.get_children():
                files.append(self.tree.item(child, "values")[0])
                
            if not files:
                self.log_message("没有文件需要处理")
                messagebox.showwarning("警告", "请先添加要处理的文件")
                return
                
            # 记录当前响度平衡参数到日志
            self.log_message("=== 响度平衡参数设置 ===")
            self.log_message(f"目标响度 (LUFS): {self.target_lufs.get()}")
            self.log_message(f"最大真峰值 (dB): {self.max_true_peak.get()}")
            self.log_message(f"响度范围 (LU): {self.loudness_range.get()}")
            self.log_message(f"处理模式: {self.loudness_mode.get()}")
            self.log_message("========================")
            
            # 响度平衡功能默认启用，无需检查
            self.log_message(f"准备对 {len(files)} 个文件进行响度平衡")
            
            # 确认是否覆盖源文件
            if self.overwrite_var.get():
                result = messagebox.askyesno("确认覆盖", "您已选择覆盖源文件，这将永久删除原始文件。是否继续？")
                if not result:
                    self.log_message("用户取消了覆盖操作")
                    return
                    
            # 在后台线程中执行响度平衡
            self.log_message("开始响度平衡任务")
            threading.Thread(target=self.process_loudness_normalization, args=(files,), daemon=True).start()
        except Exception as e:
            error_msg = f"启动响度平衡时出错: {e}"
            self.log_message(error_msg)
            messagebox.showerror("错误", error_msg)
            
    def process_loudness_normalization(self, files):
        """执行文件响度平衡处理"""
        try:
            total_files = len(files)
            completed_files = 0
            
            self.status_var.set(f"正在处理... (0/{total_files})")
            self.progress_bar.set(0)
            self.after(0, self.log_message, f"开始批量响度平衡，共 {total_files} 个文件")
            
            # 单线程顺序处理
            for i, file in enumerate(files):
                try:
                    self.after(0, self.log_message, f"开始处理文件 {i+1}/{total_files}: {os.path.basename(file)}")
                    
                    # 应用统一的音频增强处理
                    self.after(0, self.log_message, f"应用音频增强处理: {os.path.basename(file)}")
                    result = self.apply_loudness_normalization(file, None)
                    
                    # 更新UI状态
                    self.after(0, self.update_file_status, file, result)
                    self.after(0, self.log_message, f"文件响度平衡完成: {os.path.basename(file)} - {result}")
                except Exception as e:
                    error_result = f"错误: {str(e)}"
                    self.after(0, self.update_file_status, file, error_result)
                    self.after(0, self.log_message, f"文件响度平衡失败: {os.path.basename(file)} - {error_result}")
                
                # 更新进度
                completed_files += 1
                progress = completed_files / total_files
                self.progress_bar.set(progress)
                self.status_var.set(f"正在处理... ({completed_files}/{total_files})")
                    
            self.status_var.set("响度平衡完成")
            self.progress_bar.set(1.0)
            self.after(0, self.log_message, "所有文件响度平衡完成")
            
            # 显示完成消息
            self.after(0, lambda: messagebox.showinfo("完成", f"已完成 {total_files} 个文件的响度平衡"))
        except Exception as e:
            error_msg = f"批量响度平衡过程出错: {e}"
            self.after(0, self.log_message, error_msg)
            self.after(0, lambda: messagebox.showerror("错误", error_msg))
            
    # 移除 analyze_loudness 和 extract_loudnorm_json 方法，因为不再需要预分析
            
    def apply_loudness_normalization(self, file_path, loudness_info):
        """应用响度平衡处理"""
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return "失败: 文件不存在"
                
            # 获取文件信息
            file_dir = os.path.dirname(file_path)
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            file_ext = os.path.splitext(file_path)[1]
            
            # 确定输出路径 - 使用程序目录下的临时文件夹
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_output")
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)
                
            # 使用安全的文件名（无特殊字符）
            safe_filename = re.sub(r'[^\w\-_\.]', '_', file_name)
            
            if self.overwrite_var.get():
                # 覆盖源文件，先转码为临时文件
                output_path = os.path.join(temp_dir, f"{safe_filename}_temp{file_ext}")
                final_path = file_path
            else:
                # 不覆盖源文件，添加_normalized后缀
                output_path = os.path.join(temp_dir, f"{safe_filename}_normalized{file_ext}")
                final_path = os.path.join(file_dir, f"{file_name}_normalized{file_ext}")
            
            self.log_message(f"临时输出路径: {output_path}")
            
            # 构建FFmpeg命令进行响度平衡处理
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-i", file_path,
                "-map", "0",  # 映射所有流
                "-avoid_negative_ts", "make_zero",  # 避免负时间戳
                "-fflags", "+genpts",  # 重新生成时间戳
            ]
            
            # 构建滤镜链
            filters = []
            
            # 1. 人声清晰度增强 (EQ)
            if self.enable_eq.get():
                # highpass=f=80: 去除80Hz以下的低频噪音
                # lowshelf=g=-2:f=300: 稍微衰减300Hz附近的浑浊感
                # equalizer=f=3000:t=q:w=1:g=3: 提升3kHz附近的人声清晰度
                filters.append("highpass=f=80,lowshelf=g=-2:f=300,equalizer=f=3000:t=q:w=1:g=3")
            
            # 2. 动态均衡 (dynaudnorm) - 解决忽大忽小
            filters.append("dynaudnorm=f=500:g=31:p=0.95:m=10.0:r=0.9")
            
            # 3. 目标响度标准化 (loudnorm) - 统一输出电平
            filters.append(f"loudnorm=I={self.target_lufs.get()}:TP={self.max_true_peak.get()}:LRA={self.loudness_range.get()}:print_format=json")
            
            # 组合滤镜
            filter_str = ",".join(filters)
            cmd.extend(["-af", filter_str])
            
            # 根据文件类型添加适当的编码器参数
            # 音频编码参数
            audio_args = ["-c:a", "aac", "-b:a", self.audio_bitrate.get()]
            
            # 采样率
            if self.sample_rate.get() != "自动":
                audio_args.extend(["-ar", self.sample_rate.get()])
                
            # 声道
            if self.audio_channels.get() != "自动":
                if "立体声" in self.audio_channels.get():
                    audio_args.extend(["-ac", "2"])
                elif "单声道" in self.audio_channels.get():
                    audio_args.extend(["-ac", "1"])
            
            # 根据文件类型添加适当的编码器参数
            if file_path.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm')):
                # 视频文件 - 复制视频流，只处理音频
                cmd.extend(["-c:v", "copy"])  # 复制视频流
                cmd.extend(audio_args)
            else:
                # 音频文件 - 统一输出为AAC格式
                cmd.extend(audio_args)
                # 如果原文件不是AAC格式，需要修改输出路径
                if not file_ext.lower() == '.aac':
                    output_path = output_path.replace(file_ext, '.aac')
                    final_path = final_path.replace(file_ext, '.aac')
                    self.log_message(f"音频文件响度平衡后输出为AAC格式（128k码率）")
            
            # 添加输出路径
            cmd.append(output_path)
            
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            try:
                if not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                    self.log_message(f"创建输出目录: {output_dir}")
            except Exception as e:
                self.log_message(f"创建输出目录失败: {str(e)}")
                return f"失败: 无法创建输出目录 - {str(e)}"
                
            # 执行FFmpeg命令
            if os.name == 'nt':
                result = subprocess.run(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=False,
                    timeout=600,  # 10分钟超时
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                stderr_text = result.stderr.decode('utf-8', errors='ignore')
            else:
                result = subprocess.run(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    encoding='utf-8',
                    errors='ignore',
                    timeout=600
                )
                stderr_text = result.stderr
            
            # 处理结果
            if result.returncode == 0:
                try:
                    # 确保目标目录存在
                    final_dir = os.path.dirname(final_path)
                    if not os.path.exists(final_dir):
                        os.makedirs(final_dir, exist_ok=True)
                        
                    # 复制文件到最终位置
                    import shutil
                    
                    # 如果是覆盖源文件且格式发生了变化（如MP3->WAV）
                    if self.overwrite_var.get():
                        # 删除原文件（可能是不同格式）
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            self.log_message(f"已删除原文件: {file_path}")
                        
                        # 将处理后的文件复制到原文件位置（但可能是新格式）
                        self.log_message(f"处理成功，正在将文件从 {output_path} 复制到 {final_path}")
                        shutil.copy2(output_path, final_path)
                    else:
                        # 不覆盖源文件，直接复制到目标位置
                        self.log_message(f"处理成功，正在将文件从 {output_path} 复制到 {final_path}")
                        shutil.copy2(output_path, final_path)
                    
                    # 删除临时文件
                    os.remove(output_path)
                    
                    if self.overwrite_var.get():
                        return "完成 (已覆盖源文件)"
                    else:
                        return "完成"
                except Exception as e:
                    self.log_message(f"复制文件失败: {str(e)}")
                    return f"完成 (复制文件时出错: {str(e)})"
            else:
                # 删除临时文件（如果存在）
                if os.path.exists(output_path):
                    os.remove(output_path)
                
                # 如果是MP3文件且使用mp3_mf编码器失败，尝试使用AAC编码器作为回退
                if (file_ext.lower() == '.mp3' and 
                    "mp3_mf" in str(cmd) and 
                    "Error while opening encoder" in stderr_text):
                    
                    self.log_message("mp3_mf编码器失败，尝试使用AAC编码器作为回退")
                    
                    # 为AAC编码器创建新的输出路径（使用.aac扩展名）
                    fallback_output_path = output_path.replace('.mp3', '.aac')
                    fallback_final_path = final_path.replace('.mp3', '.aac')
                    
                    # 重新构建命令，使用AAC编码器
                    fallback_cmd = [
                        "ffmpeg",
                        "-y",  # 覆盖输出文件
                        "-i", file_path,
                        "-af", filter_str,
                        "-c:a", "aac", "-b:a", "128k",
                        fallback_output_path
                    ]
                    
                    # 重新执行命令
                    try:
                        if os.name == 'nt':
                            fallback_result = subprocess.run(
                                fallback_cmd, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE, 
                                text=False,
                                timeout=600,
                                creationflags=subprocess.CREATE_NO_WINDOW
                            )
                            fallback_stderr = fallback_result.stderr.decode('utf-8', errors='ignore')
                        else:
                            fallback_result = subprocess.run(
                                fallback_cmd, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE, 
                                text=True, 
                                encoding='utf-8',
                                errors='ignore',
                                timeout=600
                            )
                            fallback_stderr = fallback_result.stderr
                        
                        if fallback_result.returncode == 0:
                            self.log_message("使用AAC编码器回退成功")
                            # 继续处理成功的情况
                            try:
                                # 确保目标目录存在
                                final_dir = os.path.dirname(fallback_final_path)
                                if not os.path.exists(final_dir):
                                    os.makedirs(final_dir, exist_ok=True)
                                    
                                # 如果是覆盖源文件，先删除原文件
                                if self.overwrite_var.get() and os.path.exists(fallback_final_path):
                                    os.remove(fallback_final_path)
                                    
                                # 复制文件到最终位置
                                import shutil
                                self.log_message(f"处理成功，正在将文件从 {fallback_output_path} 复制到 {fallback_final_path}")
                                shutil.copy2(fallback_output_path, fallback_final_path)
                                
                                # 删除临时文件
                                os.remove(fallback_output_path)
                                
                                if self.overwrite_var.get():
                                    return "完成 (已覆盖源文件，使用AAC编码)"
                                else:
                                    return "完成 (使用AAC编码)"
                            except Exception as e:
                                self.log_message(f"复制文件失败: {str(e)}")
                                return f"完成 (复制文件时出错: {str(e)})"
                        else:
                            self.log_message("AAC编码器回退也失败")
                    except Exception as e:
                        self.log_message(f"回退尝试失败: {str(e)}")
                
                # 提取关键错误信息
                error_msg = f"FFmpeg失败 (返回码: {result.returncode})"
                if stderr_text:
                    # 提取关键错误信息
                    error_lines = stderr_text.split('\n')
                    key_errors = [line for line in error_lines if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'cannot', 'unable'])]
                    if key_errors:
                        error_msg += f" - {'; '.join(key_errors[:2])}"  # 只显示前2个关键错误
                    else:
                        error_msg += f" - {stderr_text[:100]}"  # 如果没有关键错误，显示前100字符
                return f"失败: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return f"失败: 处理超时（超过10分钟）"
        except Exception as e:
            return f"错误: {str(e)}"
            
    def update_file_status(self, file_path, status):
        """更新文件状态"""
        # 查找对应的Treeview项目并更新状态
        for child in self.tree.get_children():
            if self.tree.item(child, "values")[0] == file_path:
                self.tree.item(child, values=(file_path, status))
                break
    
                
if __name__ == "__main__":
    app = TranscoderApp()
    app.mainloop()