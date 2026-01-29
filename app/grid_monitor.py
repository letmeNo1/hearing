import cv2
import numpy as np
import json
import os
import time
import threading
from tkinter import Toplevel, Label, Button
import tkinter as tk
import tkinter.messagebox as messagebox
from PIL import Image, ImageTk

# 配置常量
PARAMS_FILE = "calibration_params.json"
HEARING_AID_BORDER_DATA = "hearing_aid_border.json"
CHARGING_CASE_BORDER_DATA = "charging_case_border.json"
BRIGHTNESS_ROOT_DIR = "brightness_logs"  # 亮度日志根文件夹
CHARGING_ROOT_DIR = "charging_log"       # 充电状态日志根文件夹
CAM_WIDTH, CAM_HEIGHT = 1920, 1080

# 亮度检测配置
BRIGHT_THRESHOLD = 35
BRIGHT_PIXEL_RATIO = 0.001
DILATE_KERNEL_SIZE = (5, 5)

# 充电盒逐格分析配置（仅作用于充电盒）
ANALYSIS_INTERVAL = 4    # 每4秒分析一次
CACHE_DURATION = 4       # 分析过去4秒的数据
STABILITY_THRESHOLD = 0.05  # 常亮判定：亮度波动<5%
START_DELAY = 5          # 启动后延迟5秒再开始检测分析
GRID_COUNT = 20          # 充电盒总网格数（4行5列=20格）

class GridMonitor:
    def __init__(self, root, monitor_type):
        self.root = root
        self.monitor_type = monitor_type
        self.is_running = False
        self.cap = None
        self.M = None
        self.size = (CAM_WIDTH, CAM_HEIGHT)
        self.border_rect = None
        self.grid_regions = []
        self.monitor_win = None
        
        # 仅充电盒初始化相关变量
        self.grid_brightness_cache = []
        self.start_time = 0  # 程序启动时间（用于5秒延迟）
        self.restart_timestamp = ""  # 本次重启的时间戳（YYYYMMDD_HHMMSS）
        if self.monitor_type == "charging_case":
            self.grid_brightness_cache = [[] for _ in range(GRID_COUNT)]
            # 生成本次重启的唯一时间戳（精确到秒，避免重复）
            self.restart_timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            # 启动前创建根文件夹 + 本次重启的子文件夹
            self._create_root_dirs()
            self._create_restart_subdirs()
        self.last_analysis_time = 0  # 上次分析时间戳

    def _create_root_dirs(self):
        """创建亮度/充电状态日志根文件夹（不存在则创建）"""
        try:
            os.makedirs(BRIGHTNESS_ROOT_DIR, exist_ok=True)
            os.makedirs(CHARGING_ROOT_DIR, exist_ok=True)
        except Exception as e:
            messagebox.showerror("文件夹创建失败", f"根文件夹创建失败：{str(e)}")

    def _create_restart_subdirs(self):
        """创建本次重启的子文件夹（亮度/充电日志目录下各一个）"""
        if self.monitor_type != "charging_case":
            return
        # 亮度日志重启子文件夹：brightness_logs/重启时间戳/
        brightness_restart_dir = os.path.join(BRIGHTNESS_ROOT_DIR, self.restart_timestamp)
        # 充电日志重启子文件夹：charging_log/重启时间戳/
        charging_restart_dir = os.path.join(CHARGING_ROOT_DIR, self.restart_timestamp)
        try:
            os.makedirs(brightness_restart_dir, exist_ok=True)
            os.makedirs(charging_restart_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("文件夹创建失败", f"重启子文件夹创建失败：{str(e)}")

    def _get_10min_segment(self):
        """获取当前10分钟时间段的标识（YYYYMMDD_HHMM_HHMM）"""
        now = time.localtime()
        year, month, day = now.tm_year, now.tm_mon, now.tm_mday
        hour, minute = now.tm_hour, now.tm_min

        start_minute = (minute // 10) * 10
        end_minute = start_minute + 10
        start_h, end_h = hour, hour
        start_d, end_d = day, day
        
        # 处理跨小时/跨天情况
        if end_minute >= 60:
            end_minute = 0
            end_h += 1
            if end_h >= 24:
                end_h = 0
                end_d += 1
                if end_d > 31:  # 简单处理跨月，实际可优化
                    end_d = 1
                    end_h = 0

        # 格式化时间字符串（补零）
        date_str = f"{year:04d}{month:02d}{start_d:02d}"
        start_time_str = f"{start_h:02d}{start_minute:02d}"
        end_time_str = f"{end_h:02d}{end_minute:02d}"
        return f"{date_str}_{start_time_str}_{end_time_str}"

    def get_10min_log_filename(self):
        """获取当前10分钟段的亮度日志文件名（仅充电盒）"""
        if self.monitor_type != "charging_case":
            return ""
        # 路径：brightness_logs/重启时间戳/10分钟分段.json
        segment = self._get_10min_segment()
        restart_dir = os.path.join(BRIGHTNESS_ROOT_DIR, self.restart_timestamp)
        return os.path.join(restart_dir, f"{segment}.json")

    def get_charging_status_filename(self):
        """获取当前10分钟段的充电状态日志文件名（仅充电盒）"""
        if self.monitor_type != "charging_case":
            return ""
        # 路径：charging_log/重启时间戳/10分钟分段.log
        segment = self._get_10min_segment()
        restart_dir = os.path.join(CHARGING_ROOT_DIR, self.restart_timestamp)
        return os.path.join(restart_dir, f"{segment}.log")

    def load_config(self):
        if os.path.exists(PARAMS_FILE):
            with open(PARAMS_FILE, 'r') as f:
                d = json.load(f)
                self.M = np.array(d['perspective_matrix'])
                self.size = tuple(d['cropped_size'])

        border_file = HEARING_AID_BORDER_DATA if self.monitor_type == "hearing_aid" else CHARGING_CASE_BORDER_DATA
        if os.path.exists(border_file):
            with open(border_file, 'r') as f:
                d = json.load(f)
                self.border_rect = d['contours'][0]['bounding_rect']
        else:
            raise Exception(f"未找到{self.monitor_type}边框配置文件: {border_file}")

    def init_grid_regions(self):
        self.grid_regions.clear()
        x, y, w, h = self.border_rect
        index = 0

        if self.monitor_type == "hearing_aid":
            y_off = int(h * 0.05)
            ys, ye, nh = y + y_off, y + h - y_off, h - 2 * y_off
            gw, xs = w / 14, int(x + (w / 14) / 2)
            for row in range(4):
                row_y1 = int(ys + row * (nh / 4))
                row_y2 = int(ys + (row + 1) * (nh / 4))
                for col in range(14):
                    col_x1 = int(xs + col * gw)
                    col_x2 = int(xs + (col + 1) * gw)
                    self.grid_regions.append((col_x1, row_y1, col_x2, row_y2, index))
                    index += 1

        elif self.monitor_type == "charging_case":
            # 充电盒网格为4行5列（20格）- 修复语法错误
            gw = w / 5    # 每列宽度 = 总宽度 / 5
            gh = h / 4    # 每行高度 = 总高度 / 4
            # 遍历4行
            for row in range(4):
                row_y1 = int(y + row * gh)
                row_y2 = int(y + (row + 1) * gh)
                # 遍历5列
                for col in range(5):
                    col_x1 = int(x + col * gw)
                    col_x2 = int(x + (col + 1) * gw)  # 修复原语法错误
                    self.grid_regions.append((col_x1, row_y1, col_x2, row_y2, index))
                    index += 1

    def calculate_grid_bright(self, frame):
        bright_grids = []
        grid_brightness = []
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_gray = cv2.GaussianBlur(frame_gray, (5, 5), 0)

        # 先膨胀再二值化，强化小亮点
        kernel = np.ones(DILATE_KERNEL_SIZE, np.uint8)
        frame_gray = cv2.dilate(frame_gray, kernel, iterations=1)

        _, frame_binary = cv2.threshold(frame_gray, BRIGHT_THRESHOLD, 255, cv2.THRESH_BINARY)

        for (x1, y1, x2, y2, idx) in self.grid_regions:
            grid_dilated = frame_binary[y1:y2, x1:x2]
            total_pixels = grid_dilated.size
            if total_pixels == 0:
                grid_brightness.append(0)
                continue

            bright_pixels = np.count_nonzero(grid_dilated)
            bright_ratio = bright_pixels / total_pixels
            grid_brightness.append(bright_ratio)

            if bright_ratio >= BRIGHT_PIXEL_RATIO:
                bright_grids.append(idx)

        # 仅充电盒场景更新逐格缓存
        if self.monitor_type == "charging_case":
            current_time = time.time()
            # 遍历20个格子，更新对应缓存
            for grid_idx in range(GRID_COUNT):
                # 确保索引不越界（兼容配置异常情况）
                brightness = grid_brightness[grid_idx] if grid_idx < len(grid_brightness) else 0.0
                self.grid_brightness_cache[grid_idx].append((current_time, brightness))

        return bright_grids, grid_brightness, frame_binary

    def clean_expired_cache(self):
        """仅充电盒清理过期缓存：移除每个格子超过4秒的亮度数据"""
        if self.monitor_type != "charging_case":
            return
        current_time = time.time()
        for grid_idx in range(GRID_COUNT):
            # 保留4秒内的数据
            self.grid_brightness_cache[grid_idx] = [
                item for item in self.grid_brightness_cache[grid_idx]
                if current_time - item[0] <= CACHE_DURATION
            ]

    def analyze_single_grid_status(self, grid_idx):
        """分析单个格子的充电状态（仅充电盒）
        返回：(状态描述, 详细信息)
        状态：充电完成/充电中/无状态
        """
        cache = self.grid_brightness_cache[grid_idx]
        if len(cache) < 3:  # 数据不足，先判定为无状态（5秒后数据足够会修正）
            return "无状态", "数据不足（启动延迟期）"
        
        # 提取缓存中的亮度值
        brightness_list = [item[1] for item in cache]
        # 计算平均亮度
        brightness_mean = np.mean(brightness_list)
        
        # 判定1：无状态 - 亮度低于检测阈值（灯没亮）
        if brightness_mean < BRIGHT_PIXEL_RATIO:
            return "无状态", f"亮度低于阈值（均值{brightness_mean:.4f} < {BRIGHT_PIXEL_RATIO}）"
        
        # 计算亮度波动（标准差/均值）
        brightness_std = np.std(brightness_list)
        stability_ratio = brightness_std / brightness_mean if brightness_mean > 0 else 1.0

        # 判定2：充电完成 - 亮度稳定（波动<5%）
        if stability_ratio < STABILITY_THRESHOLD:
            return "充电完成", f"常亮（亮度波动{stability_ratio:.4f} < 5%）"
        
        # 判定3：充电中 - 只要亮度达标且不稳定（不管波动/渐变/跳动）
        # 补充判断渐变方向（可选，仅用于日志说明）
        x = np.arange(len(brightness_list))
        slope, _ = np.polyfit(x, brightness_list, 1)
        if slope > 0:
            trend = "亮度上升"
        elif slope < 0:
            trend = "亮度下降"
        else:
            trend = "亮度跳动"
        
        return "充电中", f"{trend}（波动{stability_ratio:.4f} ≥ 5%）"

    def analyze_charging_case_status(self):
        """分析充电盒20个格子的状态，输出并写入日志"""
        if self.monitor_type != "charging_case":
            return
        
        # 检查是否过了5秒启动延迟
        current_time = time.time()
        if current_time - self.start_time < START_DELAY:
            return  # 未到延迟时间，跳过分析
        
        # 清理过期缓存
        self.clean_expired_cache()
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # 构建状态日志内容
        log_content = f"===== 充电盒状态分析 [{timestamp}] =====\n"
        log_content += f"重启标识：{self.restart_timestamp}\n"
        print(f"\n===== 充电盒状态分析 [{timestamp}] =====")
        print(f"重启标识：{self.restart_timestamp}")
        
        # 遍历20个格子逐个分析
        for grid_idx in range(GRID_COUNT):
            status, detail = self.analyze_single_grid_status(grid_idx)
            grid_log = f"网格{grid_idx:02d}：{status} - {detail}"
            log_content += grid_log + "\n"
            print(grid_log)
        
        log_content += "=======================================\n\n"
        print("=======================================")
        
        # 获取当前10分钟段的充电状态日志文件
        charging_log_file = self.get_charging_status_filename()
        if not charging_log_file:
            return
        # 写入充电状态日志文件（追加模式）
        try:
            with open(charging_log_file, 'a', encoding='utf-8') as f:
                f.write(log_content)
        except Exception as e:
            messagebox.showwarning("状态日志写入失败", f"充电盒状态日志保存失败：{str(e)}")

    def log_change(self, bright_grids, grid_brightness):
        if not bright_grids or self.monitor_type != "charging_case":
            return

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry = {
            "timestamp": timestamp,
            "monitor_type": self.monitor_type,
            "bright_grids": bright_grids,
            "grid_brightness": grid_brightness,
            "total_bright_grids": len(bright_grids),
            "restart_timestamp": self.restart_timestamp  # 记录本次重启标识
        }

        # 获取当前10分钟段的亮度日志文件路径
        log_file = self.get_10min_log_filename()
        if not log_file:
            return

        # 写入JSON日志（追加模式）
        try:
            # 读取现有日志（文件不存在则创建空列表）
            logs = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            # 添加新日志条目
            logs.append(log_entry)
            # 写入文件
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showwarning("日志写入失败", f"亮度日志保存失败：{str(e)}")

    def draw_grid_and_bright(self, frame, bright_grids):
        x, y, w, h = self.border_rect
        if self.monitor_type == "hearing_aid":
            y_off = int(h * 0.05)
            ys, ye, nh = y + y_off, y + h - y_off, h - 2 * y_off
            gw, xs = w / 14, int(x + (w / 14) / 2)
            for i in range(14):
                cx = int(xs + i * gw)
                cv2.line(frame, (cx, ys), (cx, ye), (255, 0, 255), 2)
            for i in range(5):
                cy = int(ys + i * (nh / 4))
                cv2.line(frame, (xs, cy), (int(xs + 13 * gw), cy), (255, 0, 255), 2)
        elif self.monitor_type == "charging_case":
            # 4行5列网格绘制
            gw = w / 5
            gh = h / 4
            # 竖线（5列=6条线）
            for i in range(6):
                cv2.line(frame, (int(x + i * gw), y), (int(x + i * gw), y + h), (255, 255, 255), 2)
            # 横线（4行=5条线）
            for i in range(5):
                cv2.line(frame, (x, int(y + i * gh)), (x + w, int(y + i * gh)), (255, 255, 255), 2)

        # 标注亮网格
        for (x1, y1, x2, y2, idx) in self.grid_regions:
            if idx in bright_grids:
                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
                alpha = 0.3
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
                cv2.putText(frame, str(idx), (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame

    def stop_monitor(self):
        self.is_running = False

    def run_monitor(self):
        try:
            self.load_config()
            self.init_grid_regions()
        except Exception as e:
            messagebox.showerror("初始化失败", f"加载配置出错: {str(e)}")
            return

        # 初始化摄像头
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

        # 记录程序启动时间（用于5秒延迟）
        self.start_time = time.time()

        # 创建监控窗口
        self.monitor_win = Toplevel(self.root)
        self.monitor_win.title(f"{('助听器' if self.monitor_type == 'hearing_aid' else '充电盒')}网格监控")
        self.monitor_win.geometry("900x600")
        self.monitor_win.protocol("WM_DELETE_WINDOW", self.stop_monitor)

        # 视频显示区域
        video_label = Label(self.monitor_win)
        video_label.pack(side="top", padx=10, pady=10, fill="both", expand=True)

        # 停止按钮
        stop_btn = Button(self.monitor_win, text="停止监控", bg="#f44336", fg="white",
                          font=("微软雅黑", 12, "bold"), command=self.stop_monitor)
        stop_btn.pack(side="bottom", fill="x", padx=10, pady=10)

        # 监控主循环
        self.is_running = True
        self.last_analysis_time = time.time()
        
        while self.is_running:
            ret, raw = self.cap.read()
            if not ret:
                break

            # 透视变换校正
            frame = cv2.warpPerspective(raw, self.M, self.size) if self.M is not None else raw

            # 检测亮光
            bright_grids, grid_brightness, _ = self.calculate_grid_bright(frame)
            
            # 清理缓存（仅充电盒）
            self.clean_expired_cache()

            # 记录原始亮度日志（仅充电盒）
            self.log_change(bright_grids, grid_brightness)
            
            # 仅充电盒：过了5秒延迟后，每4秒分析一次状态
            current_time = time.time()
            if (self.monitor_type == "charging_case" and 
                current_time - self.start_time >= START_DELAY and 
                current_time - self.last_analysis_time >= ANALYSIS_INTERVAL):
                self.analyze_charging_case_status()
                self.last_analysis_time = current_time

            # 绘制标注
            frame = self.draw_grid_and_bright(frame, bright_grids)

            # 转换为Tkinter显示格式
            frame_show = cv2.resize(frame, (880, 520))
            frame_rgb = cv2.cvtColor(frame_show, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(frame_rgb)
            img_tk = ImageTk.PhotoImage(image=img_pil)
            video_label.config(image=img_tk)
            video_label.image = img_tk

            # 键盘退出
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.stop_monitor()

        # 释放资源
        self.cap.release()
        cv2.destroyAllWindows()
        self.monitor_win.destroy()

def start_hearing_aid_monitor(root):
    """启动助听器网格监控（无逐格状态分析）"""
    monitor = GridMonitor(root, "hearing_aid")
    threading.Thread(target=monitor.run_monitor, daemon=True).start()

def start_charging_case_monitor(root):
    """启动充电盒网格监控（含20格逐状态分析）"""
    monitor = GridMonitor(root, "charging_case")
    threading.Thread(target=monitor.run_monitor, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    # 测试充电盒监控（仅此场景有逐格状态分析）
    start_charging_case_monitor(root)
    root.mainloop()