import json
import tkinter as tk
from tkinter import messagebox, ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from datetime import datetime

# 配置常量（和监控程序保持一致）
LOG_FILE =r"C:\Users\swtest\Documents\GitHub\hearing\brightness_log.json"

class BrightnessAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("光亮变化分析工具")
        self.root.geometry("900x600")
        
        # 加载日志数据
        self.logs = self.load_logs()
        
        # 创建UI界面
        self.create_ui()
        
        # 如果有数据，默认绘制全部数据
        if self.logs:
            self.plot_brightness_curve()

    def load_logs(self):
        """加载JSON日志文件"""
        if not LOG_FILE or not os.path.exists(LOG_FILE):
            messagebox.showwarning("文件不存在", f"未找到日志文件：{LOG_FILE}\n请先运行监控程序生成日志！")
            return []
        
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return logs
        except Exception as e:
            messagebox.showerror("读取失败", f"日志文件解析错误：{str(e)}")
            return []

    def create_ui(self):
        """创建分析工具UI"""
        # 顶部控制面板
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill=tk.X, side=tk.TOP)
        
        # 标题
        title_label = ttk.Label(control_frame, text="光亮变化趋势分析", font=("微软雅黑", 16, "bold"))
        title_label.pack(pady=5)
        
        # 按钮区域
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        # 刷新数据按钮
        refresh_btn = ttk.Button(btn_frame, text="刷新数据", command=self.refresh_data)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # 导出数据按钮
        export_btn = ttk.Button(btn_frame, text="导出CSV", command=self.export_to_csv)
        export_btn.pack(side=tk.LEFT, padx=5)
        
        # 清空日志按钮（谨慎操作）
        clear_btn = ttk.Button(btn_frame, text="清空日志", command=self.clear_logs)
        clear_btn.pack(side=tk.RIGHT, padx=5)
        
        # 图表显示区域
        self.canvas_frame = ttk.Frame(self.root, padding="10")
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

    def plot_brightness_curve(self):
        """绘制光亮变化曲线图"""
        if not self.logs:
            return
        
        # 清空原有图表
        for widget in self.canvas_frame.winfo_children():
            widget.destroy()
        
        # 提取数据
        timestamps = []
        total_bright_grids = []
        monitor_types = set()
        
        # 解析时间戳并提取数据
        for log in self.logs:
            try:
                # 转换时间戳为datetime对象（便于绘图）
                ts = datetime.strptime(log["timestamp"], "%Y-%m-%d %H:%M:%S")
                timestamps.append(ts)
                total_bright_grids.append(log.get("total_bright_grids", 0))
                monitor_types.add(log.get("monitor_type", "unknown"))
            except Exception as e:
                continue
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(10, 5), dpi=100)
        
        # 绘制主曲线（亮网格数量）
        ax.plot(timestamps, total_bright_grids, 
                marker='o', markersize=4, 
                linestyle='-', linewidth=2, 
                color='#2196F3', label='亮网格数量')
        
        # 图表样式设置
        ax.set_title(f"光亮变化趋势（{','.join(monitor_types)}）", fontsize=14, fontweight='bold')
        ax.set_xlabel("时间", fontsize=12)
        ax.set_ylabel("检测到亮光的网格数量", fontsize=12)
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend(loc='upper right')
        
        # 设置Y轴为整数（网格数量不可能是小数）
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        
        # 调整布局
        plt.tight_layout()
        
        # 嵌入Tkinter窗口
        canvas = FigureCanvasTkAgg(fig, master=self.canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def refresh_data(self):
        """刷新日志数据并重新绘图"""
        self.logs = self.load_logs()
        self.plot_brightness_curve()
        messagebox.showinfo("刷新完成", "已重新加载最新日志数据！")

    def export_to_csv(self):
        """导出日志数据为CSV文件"""
        if not self.logs:
            messagebox.showwarning("无数据", "暂无日志数据可导出！")
            return
        
        import csv
        csv_file = f"brightness_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                # 写入表头
                writer.writerow(["时间戳", "监控类型", "亮网格索引", "亮网格总数"])
                # 写入数据
                for log in self.logs:
                    writer.writerow([
                        log.get("timestamp", ""),
                        log.get("monitor_type", ""),
                        ",".join(map(str, log.get("bright_grids", []))),
                        log.get("total_bright_grids", 0)
                    ])
            messagebox.showinfo("导出成功", f"数据已导出至：{csv_file}")
        except Exception as e:
            messagebox.showerror("导出失败", f"CSV导出错误：{str(e)}")

    def clear_logs(self):
        """清空日志文件（谨慎操作）"""
        if not messagebox.askyesno("确认清空", "确定要清空所有日志数据吗？此操作不可恢复！"):
            return
        
        try:
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f)
            self.logs = []
            self.plot_brightness_curve()
            messagebox.showinfo("清空完成", "日志文件已清空！")
        except Exception as e:
            messagebox.showerror("清空失败", f"清空日志错误：{str(e)}")

if __name__ == "__main__":
    import os  # 补充导入os模块
    root = tk.Tk()
    app = BrightnessAnalyzer(root)
    root.mainloop()