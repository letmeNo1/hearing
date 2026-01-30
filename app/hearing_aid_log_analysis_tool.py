# hearing_aid_log_analysis_tool.py
import os
import json
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext

# ==============================================
# 助听器日志分析核心逻辑
# ==============================================
class HearingAidLogAnalyzer:
    def __init__(self, log_root_dir):
        self.log_root_dir = log_root_dir
        self.grid_summary = {}
        self.debug_info = []  # 调试信息
        # 初始化56个网格的统计结构
        for idx in range(56):
            self.grid_summary[idx] = {
                "records": [],                  # 所有记录 (timestamp_str, datetime_obj, is_abnormal)
                "total_abnormal_times": 0,      # 异常次数
                "first_abnormal_time": None,    # 首次异常时间
                "last_abnormal_time": None,     # 最后异常时间
                "total_abnormal_duration": 0,   # 总异常时长（秒，按10分钟分段估算）
                "is_always_normal": True        # 是否全程正常（无异常）
            }

    def _safe_read_json(self, file_path):
        """安全读取JSON文件（兼容多编码）"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return json.load(f), enc
            except Exception as e:
                self.debug_info.append(f"  - 使用编码 {enc} 读取失败: {str(e)}")
                continue
        return None, None

    def _parse_single_json(self, file_path):
        """解析单个助听器JSON日志文件"""
        if not os.path.isfile(file_path):
            self.debug_info.append(f"跳过非文件: {file_path}")
            return
        
        # 读取JSON
        json_data, enc = self._safe_read_json(file_path)
        if json_data is None:
            self.debug_info.append(f"读取失败（所有编码均不兼容）: {file_path}")
            return
        self.debug_info.append(f"成功读取文件（编码:{enc}）: {file_path}")

        if not isinstance(json_data, list):
            self.debug_info.append(f"  - 无效JSON格式（非列表）: {file_path}")
            return
        
        parsed_count = 0
        for entry in json_data:
            # 验证必填字段
            required_fields = ["timestamp", "abnormal_grids", "restart_timestamp"]
            if not all(field in entry for field in required_fields):
                self.debug_info.append(f"  - 缺少必填字段: {entry}")
                continue
            
            # 解析时间戳
            try:
                ts_obj = datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S")
            except:
                self.debug_info.append(f"  - 无效时间戳: {entry['timestamp']}")
                continue
            
            # 解析异常网格
            abnormal_grids = entry.get("abnormal_grids", [])
            if not isinstance(abnormal_grids, list):
                self.debug_info.append(f"  - 异常网格格式错误: {abnormal_grids}")
                continue
            
            # 记录每个网格的异常状态
            for grid_idx in range(56):
                is_abnormal = grid_idx in abnormal_grids
                self.grid_summary[grid_idx]["records"].append((entry["timestamp"], ts_obj, is_abnormal))
                if is_abnormal:
                    self.grid_summary[grid_idx]["total_abnormal_times"] += 1
                    self.grid_summary[grid_idx]["is_always_normal"] = False
                    # 记录首次/最后异常时间
                    if self.grid_summary[grid_idx]["first_abnormal_time"] is None:
                        self.grid_summary[grid_idx]["first_abnormal_time"] = ts_obj
                    self.grid_summary[grid_idx]["last_abnormal_time"] = ts_obj
            
            parsed_count += 1
        
        self.debug_info.append(f"  - 成功解析条目数: {parsed_count}")

    def _scan_all_log_files(self):
        """递归扫描所有助听器JSON日志"""
        self.debug_info.append(f"\n开始扫描目录: {self.log_root_dir}")
        log_files = []
        for root_dir, _, files in os.walk(self.log_root_dir):
            for fn in files:
                if fn.lower().endswith(".json"):
                    full_path = os.path.join(root_dir, fn)
                    log_files.append(full_path)
        self.debug_info.append(f"找到.json文件数量: {len(log_files)}")
        self.debug_info.append(f"文件列表: {log_files}")
        
        # 解析每个文件
        for fp in log_files:
            self._parse_single_json(fp)

    def _compute_grid_stats(self):
        """计算每个网格的异常统计"""
        self.debug_info.append("\n开始计算网格异常统计...")
        total_records = 0
        for idx in range(56):
            d = self.grid_summary[idx]
            records = d["records"]
            total_records += len(records)
            if not records:
                self.debug_info.append(f"网格 {idx:02d}: 无解析记录")
                continue

            # 按时间排序
            records_sorted = sorted(records, key=lambda x: x[1])
            d["records"] = records_sorted

            # 估算异常总时长（假设每条记录间隔约1秒）
            abnormal_durations = []
            prev_time = None
            for ts_str, ts_obj, is_abnormal in records_sorted:
                if prev_time and is_abnormal:
                    delta = ts_obj - prev_time
                    abnormal_durations.append(delta.total_seconds())
                prev_time = ts_obj
            if abnormal_durations:
                d["total_abnormal_duration"] = sum(abnormal_durations)
        
        self.debug_info.append(f"总解析记录数: {total_records}")

    def analyze(self):
        """统一分析入口"""
        if not os.path.isdir(self.log_root_dir):
            raise Exception(f"目录不存在: {self.log_root_dir}")
        self._scan_all_log_files()
        self._compute_grid_stats()

    def generate_report(self):
        """生成分析报告（中文界面+核心英文）"""
        header = "=" * 100
        # 调试信息
        debug_part = [
            "[调试信息]",
            "----------",
            "\n".join(self.debug_info),
            "\n" + header
        ]
        
        # 核心报告
        core_report = [
            "助听器网格异常分析报告（基于JSON日志）",
            f"分析目录: {self.log_root_dir}",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            header,
            "",
            "说明：",
            "  - 正常状态：网格长暗（bright_ratio < 0.001）",
            "  - 异常状态：网格出现亮度波动（bright_ratio ≥ 0.001）",
            "  - 异常时长：按日志记录时间间隔估算（单位：秒）",
            "",
            header
        ]

        # 网格详情
        grid_part = []
        for idx in range(56):
            d = self.grid_summary[idx]
            grid_title = f"网格 {idx:02d}"
            
            # 异常次数
            abnormal_times = d["total_abnormal_times"]
            # 首次/最后异常时间
            first_ab = d["first_abnormal_time"].strftime("%Y-%m-%d %H:%M:%S") if d["first_abnormal_time"] else "无"
            last_ab = d["last_abnormal_time"].strftime("%Y-%m-%d %H:%M:%S") if d["last_abnormal_time"] else "无"
            # 总异常时长
            if d["total_abnormal_duration"] > 0:
                mins = int(d["total_abnormal_duration"] // 60)
                secs = d["total_abnormal_duration"] % 60
                duration_str = f"{mins}分 {secs:.2f}秒"
            else:
                duration_str = "0秒"
            # 全程正常标记
            always_normal = "是" if d["is_always_normal"] else "否"

            # 构建网格信息
            grid_part.append(f"{grid_title}:")
            grid_part.append(f"  异常次数: {abnormal_times} | 全程正常: {always_normal}")
            grid_part.append(f"  首次异常时间: {first_ab}")
            grid_part.append(f"  最后异常时间: {last_ab}")
            grid_part.append(f"  总异常时长: {duration_str}")
            grid_part.append("-" * 100)

        # 合并报告
        full_report = "\n".join(debug_part + core_report + grid_part)
        return full_report

    def save_report(self, save_path="hearing_aid_grid_analysis_report.txt"):
        """保存报告"""
        rep = self.generate_report()
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(rep)
        return save_path

# ==============================================
# GUI界面（中文）
# ==============================================
def open_hearing_aid_analyzer_window(parent_root):
    win = tk.Toplevel(parent_root)
    win.title("助听器日志分析工具（异常：亮度波动）")
    win.geometry("900x700")
    win.resizable(True, True)

    # 路径选择
    tk.Label(win, text="选择助听器日志根目录（hearing_aid_brightness_log）：", font=("微软雅黑", 11)).pack(pady=8)
    path_frame = tk.Frame(win)
    path_frame.pack(fill=tk.X, padx=20, pady=4)
    
    log_path_var = tk.StringVar(value="./hearing_aid_brightness_log")
    path_entry = tk.Entry(path_frame, textvariable=log_path_var, font=("微软雅黑", 10))
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def select_folder():
        """浏览文件夹"""
        dir_choose = filedialog.askdirectory(title="选择助听器日志目录", parent=win)
        if dir_choose:
            log_path_var.set(dir_choose)

    tk.Button(path_frame, text="浏览文件夹", bg="#42A5F5", fg="white", command=select_folder).pack(side=tk.RIGHT)

    # 结果显示框
    result_box = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap=tk.WORD)
    result_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
    result_box.config(state=tk.DISABLED)

    # 分析执行
    def run_analyze():
        """执行分析"""
        target_dir = log_path_var.get().strip()
        if not target_dir:
            messagebox.showwarning("提示", "请选择日志目录", parent=win)
            return

        btn_start.config(state=tk.DISABLED, text="分析中...")
        result_box.config(state=tk.NORMAL)
        result_box.delete(1.0, tk.END)
        result_box.insert(tk.END, f"正在分析：{target_dir}\n\n请稍候...")
        result_box.config(state=tk.DISABLED)

        def task():
            """后台任务"""
            error_msg = ""
            report_content = ""
            save_path = ""
            try:
                analyzer = HearingAidLogAnalyzer(target_dir)
                analyzer.analyze()
                report_content = analyzer.generate_report()
                save_path = analyzer.save_report()
            except Exception as e:
                error_msg = str(e)

            # 线程安全更新UI
            if error_msg:
                win.after(0, lambda: show_err(error_msg))
            else:
                win.after(0, lambda: show_success(report_content, save_path))

        def show_err(msg):
            """显示错误"""
            result_box.config(state=tk.NORMAL)
            result_box.delete(1.0, tk.END)
            result_box.insert(tk.END, f"分析失败：\n{msg}")
            result_box.config(state=tk.DISABLED)
            btn_start.config(state=tk.NORMAL, text="开始分析")
            messagebox.showerror("错误", msg, parent=win)

        def show_success(report, path):
            """显示成功结果"""
            result_box.config(state=tk.NORMAL)
            result_box.delete(1.0, tk.END)
            result_box.insert(tk.END, report)
            result_box.config(state=tk.DISABLED)
            btn_start.config(state=tk.NORMAL, text="开始分析")
            messagebox.showinfo("完成", f"分析完成，报告已保存至：\n{path}", parent=win)

        # 启动后台线程
        threading.Thread(target=task, daemon=True).start()

    # 开始分析按钮
    btn_start = tk.Button(
        win, text="开始分析", bg="#4CAF50", fg="white",
        font=("微软雅黑", 12, "bold"), command=run_analyze
    )
    btn_start.pack(pady=8)

# 独立运行入口
if __name__ == "__main__":
    root_app = tk.Tk()
    root_app.withdraw()
    open_hearing_aid_analyzer_window(root_app)
    root_app.mainloop()