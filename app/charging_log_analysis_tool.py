# charging_log_analysis_tool.py
import os
import re
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext

# ==============================================
# 适配你真实日志的充电分析核心逻辑（带调试）
# ==============================================
class ChargingLogAnalyzer:
    def __init__(self, log_root_dir):
        self.log_root_dir = log_root_dir
        self.grid_summary = {}
        self.debug_info = []  # 调试信息：记录找到的文件、解析行数等
        # 初始化20个网格完整统计结构
        for idx in range(20):
            self.grid_summary[idx] = {
                "records": [],                  # 所有 (timestamp_str, datetime_obj, status)
                "initial_status": "无数据",      # 第一条状态
                "final_status": "无数据",        # 最后一条状态
                "first_charging_time": None,     # 首次【充电中】时间（开始充电）
                "first_complete_time": None,     # 首次【充电完成】时间（充电结束）
                "cost_seconds": None,            # 充电耗时(秒)
                "has_fallback": False,           # 是否回退：完成后变充电中/无状态
                "is_initial_complete": False     # 一开始就是充电完成（无充电过程）
            }

    def _safe_read_file(self, file_path):
        """兼容多编码读取文件（解决编码导致的读取失败）"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.read(), enc
            except:
                continue
        return "", None

    def _parse_single_log(self, file_path):
        """解析单个log文件，放宽正则+输出调试信息"""
        if not os.path.isfile(file_path):
            self.debug_info.append(f"跳过非文件: {file_path}")
            return
        
        # 读取文件（兼容编码）
        content, enc = self._safe_read_file(file_path)
        if not content:
            self.debug_info.append(f"读取失败（所有编码都不兼容）: {file_path}")
            return
        self.debug_info.append(f"成功读取文件（编码:{enc}）: {file_path}")

        # 放宽正则匹配规则（适配日志格式细微差异）
        # 匹配规则：[时间戳] 网格XX：状态 - 任意内容（允许空格/符号差异）
        pattern = r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*网格(\d+)\s*：\s*([^-]+?)\s*-'
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        self.debug_info.append(f"  - 匹配到日志行数: {len(matches)}")

        parsed_count = 0
        for ts_str, grid_idx_str, status in matches:
            # 网格号转换（兼容1位/2位）
            try:
                grid_idx = int(grid_idx_str)
            except:
                continue
            if grid_idx < 0 or grid_idx >= 20:
                continue
            
            # 清洗状态（去除空格、换行，只保留核心状态）
            status = status.strip().replace("\n", "").replace("\r", "")
            # 匹配核心状态（兼容多写法）
            if "无状态" in status:
                core_status = "无状态"
            elif "充电中" in status:
                core_status = "充电中"
            elif "充电完成" in status:
                core_status = "充电完成"
            else:
                continue  # 只保留三种核心状态
            
            # 解析时间对象
            try:
                ts_obj = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except:
                self.debug_info.append(f"  - 时间戳解析失败: {ts_str}")
                continue
            
            self.grid_summary[grid_idx]["records"].append((ts_str, ts_obj, core_status))
            parsed_count += 1
        self.debug_info.append(f"  - 成功解析行数: {parsed_count}")

    def _scan_all_log_files(self):
        """递归遍历所有 .log 文件 + 输出调试信息"""
        self.debug_info.append(f"\n开始遍历目录: {self.log_root_dir}")
        log_files = []
        for root_dir, _, files in os.walk(self.log_root_dir):
            for fn in files:
                if fn.lower().endswith(".log"):
                    full_path = os.path.join(root_dir, fn)
                    log_files.append(full_path)
        self.debug_info.append(f"找到.log文件数量: {len(log_files)}")
        self.debug_info.append(f"找到的文件列表: {log_files}")
        
        # 解析每个文件
        for fp in log_files:
            self._parse_single_log(fp)

    def _compute_grid_stats(self):
        """计算每个网格的充电耗时、初始状态、回退"""
        self.debug_info.append("\n开始统计网格数据...")
        total_records = 0
        for idx in range(20):
            d = self.grid_summary[idx]
            records = d["records"]
            total_records += len(records)
            if not records:
                self.debug_info.append(f"网格{idx:02d}: 无解析记录")
                continue

            # 按时间先后排序
            records_sorted = sorted(records, key=lambda x: x[1])
            d["records"] = records_sorted
            d["initial_status"] = records_sorted[0][2]
            d["final_status"] = records_sorted[-1][2]
            self.debug_info.append(f"网格{idx:02d}: 初始状态={d['initial_status']}, 最终状态={d['final_status']}, 记录数={len(records)}")

            # 1. 找首次充电中（充电开始）
            for ts_str, ts_obj, status in records_sorted:
                if status == "充电中" and d["first_charging_time"] is None:
                    d["first_charging_time"] = ts_obj

            # 2. 找首次充电完成
            for ts_str, ts_obj, status in records_sorted:
                if status == "充电完成" and d["first_complete_time"] is None:
                    d["first_complete_time"] = ts_obj

            # 3. 判断是否一开始就是满电
            if d["initial_status"] == "充电完成":
                d["is_initial_complete"] = True

            # 4. 计算耗时
            if d["first_charging_time"] and d["first_complete_time"]:
                delta = d["first_complete_time"] - d["first_charging_time"]
                d["cost_seconds"] = delta.total_seconds()

            # 5. 检测回退：一旦完成，后续出现非完成状态即为异常
            completed_flag = False
            for _, _, status in records_sorted:
                if status == "充电完成":
                    completed_flag = True
                if completed_flag and status != "充电完成":
                    d["has_fallback"] = True
                    break
        self.debug_info.append(f"总解析记录数: {total_records}")

    def analyze(self):
        """统一分析入口"""
        if not os.path.isdir(self.log_root_dir):
            raise Exception(f"目录不存在: {self.log_root_dir}")
        self._scan_all_log_files()
        self._compute_grid_stats()

    def generate_report(self):
        """生成最终统计报告（包含调试信息）"""
        header = "=" * 100
        # 调试信息前置（帮助定位问题）
        debug_part = [
            "【调试信息】",
            "----------",
            "\n".join(self.debug_info),
            "\n" + header
        ]
        
        # 核心报告
        core_report = [
            "充电盒网格充电分析报告（基于原始.log日志）",
            f"分析目录: {self.log_root_dir}",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            header,
            "",
            "格式说明:",
            "  - 首次充电时间：第一次出现【充电中】的时刻",
            "  - 首次完成时间：第一次出现【充电完成】的时刻",
            "  - 充电耗时：完成时间 - 充电开始时间",
            "  - 初始满电：监控一开始就是【充电完成】，无充电过程",
            "  - 回退异常：完成后又回到【充电中】或【无状态】",
            "",
            header
        ]

        # 逐网格输出关键信息
        grid_part = []
        for idx in range(20):
            d = self.grid_summary[idx]
            grid_title = f"网格 {idx:02d}"
            
            # 初始/最终状态
            init_st = d["initial_status"]
            final_st = d["final_status"]
            
            # 时间格式化
            first_c = d["first_charging_time"].strftime("%Y-%m-%d %H:%M:%S") if d["first_charging_time"] else "无"
            first_f = d["first_complete_time"].strftime("%Y-%m-%d %H:%M:%S") if d["first_complete_time"] else "无"
            
            # 耗时
            if d["cost_seconds"] is not None:
                mins = int(d["cost_seconds"] // 60)
                secs = d["cost_seconds"] % 60
                cost_str = f"{mins}分{secs:.2f}秒"
            else:
                cost_str = "无"
            
            # 状态标记
            initial_full = "是" if d["is_initial_complete"] else "否"
            fallback = "是" if d["has_fallback"] else "否"

            # 拼接当前网格信息
            grid_part.append(f"{grid_title}:")
            grid_part.append(f"  初始状态: {init_st}　|　最终状态: {final_st}")
            grid_part.append(f"  首次充电时间: {first_c}")
            grid_part.append(f"  首次完成时间: {first_f}")
            grid_part.append(f"  充电耗时: {cost_str}")
            grid_part.append(f"  初始满电: {initial_full}　|　回退异常: {fallback}")
            grid_part.append("-" * 100)

        # 合并所有部分
        full_report = "\n".join(debug_part + core_report + grid_part)
        return full_report

    def save_report(self, save_path="charging_grid_analysis_report.txt"):
        rep = self.generate_report()
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(rep)
        return save_path

# ==============================================
# GUI界面（无语法错误、无闭包变量错误）
# ==============================================
def open_log_analyzer_window(parent_root):
    win = tk.Toplevel(parent_root)
    win.title("充电盒日志分析工具（带调试）")
    win.geometry("900x650")
    win.resizable(True, True)

    # 路径选择
    tk.Label(win, text="选择日志根目录（charging_log）:", font=("微软雅黑", 11)).pack(pady=8)
    path_frame = tk.Frame(win)
    path_frame.pack(fill=tk.X, padx=20, pady=4)
    
    log_path_var = tk.StringVar(value="./charging_log")
    path_entry = tk.Entry(path_frame, textvariable=log_path_var, font=("微软雅黑", 10))
    path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def select_folder():
        dir_choose = filedialog.askdirectory(title="选择日志目录", parent=win)
        if dir_choose:
            log_path_var.set(dir_choose)

    tk.Button(path_frame, text="浏览文件夹", bg="#42A5F5", fg="white", command=select_folder).pack(side=tk.RIGHT)

    # 结果展示框
    result_box = scrolledtext.ScrolledText(win, font=("Consolas", 9), wrap=tk.WORD)
    result_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
    result_box.config(state=tk.DISABLED)

    # 分析执行
    def run_analyze():
        target_dir = log_path_var.get().strip()
        if not target_dir:
            messagebox.showwarning("提示", "请选择日志目录", parent=win)
            return

        btn_start.config(state=tk.DISABLED, text="分析中...")
        result_box.config(state=tk.NORMAL)
        result_box.delete(1.0, tk.END)
        result_box.insert(tk.END, f"正在分析: {target_dir}\n\n请稍候...")
        result_box.config(state=tk.DISABLED)

        def task():
            error_msg = ""
            report_content = ""
            save_path = ""
            try:
                analyzer = ChargingLogAnalyzer(target_dir)
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
            result_box.config(state=tk.NORMAL)
            result_box.delete(1.0, tk.END)
            result_box.insert(tk.END, f"分析失败:\n{msg}")
            result_box.config(state=tk.DISABLED)
            btn_start.config(state=tk.NORMAL, text="开始分析")
            messagebox.showerror("错误", msg, parent=win)

        def show_success(report, path):
            result_box.config(state=tk.NORMAL)
            result_box.delete(1.0, tk.END)
            result_box.insert(tk.END, report)
            result_box.config(state=tk.DISABLED)
            btn_start.config(state=tk.NORMAL, text="开始分析")
            messagebox.showinfo("完成", f"分析完成，报告已保存至:\n{path}", parent=win)

        threading.Thread(target=task, daemon=True).start()

    btn_start = tk.Button(
        win, text="开始分析", bg="#4CAF50", fg="white",
        font=("微软雅黑", 12, "bold"), command=run_analyze
    )
    btn_start.pack(pady=8)

# 独立运行入口
if __name__ == "__main__":
    root_app = tk.Tk()
    root_app.withdraw()
    open_log_analyzer_window(root_app)
    root_app.mainloop()