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

# 配置常量（删除 PARAMS_FILE 透视参数文件）
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HEARING_AID_BORDER_DATA = os.path.join(CURRENT_SCRIPT_DIR, "hearing_aid_border.json")
CHARGING_CASE_BORDER_DATA = os.path.join(CURRENT_SCRIPT_DIR, "charging_case_border.json")
# 新增：助听器日志根目录
HEARING_AID_BRIGHTNESS_ROOT_DIR = "hearing_aid_brightness_log"
CHARGING_BRIGHTNESS_ROOT_DIR = "brightness_logs"  # 充电盒亮度日志根文件夹
CHARGING_ROOT_DIR = "charging_log"               # 充电盒状态日志根文件夹
CAM_WIDTH, CAM_HEIGHT = 1920, 1080  # 原始帧尺寸（替代透视后的size）

# 亮度检测配置（通用）
BRIGHT_THRESHOLD = 35
BRIGHT_PIXEL_RATIO = 0.001  # 助听器异常判定阈值：超过此比例视为亮（异常）
DILATE_KERNEL_SIZE = (5, 5)

# 充电盒逐格分析配置
ANALYSIS_INTERVAL = 4    # 每4秒分析一次
CACHE_DURATION = 4       # 分析过去4秒的数据
STABILITY_THRESHOLD = 0.05  # 常亮判定：亮度波动<5%
START_DELAY = 5          # 启动后延迟5秒再开始检测分析
GRID_COUNT_CHARGING = 20 # 充电盒总网格数（4行5列=20格）
GRID_COUNT_HEARING_AID = 56 # 助听器总网格数（4行14列=56格）

# 状态枚举（英文）
STATUS_NO_STATUS = "no_status"
STATUS_CHARGING = "charging"
STATUS_CHARGED = "charged"

class GridMonitor:
    def __init__(self, root, monitor_type):
        self.root = root
        self.monitor_type = monitor_type
        self.is_running = False
        self.cap = None
        # 核心修改1：删除透视变换相关变量（self.M/self.size）
        self.border_rect = None
        self.grid_regions = []
        self.monitor_win = None
        
        # 重启时间戳（通用）
        self.restart_timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        self.start_time = 0  # 程序启动时间
        self.last_analysis_time = 0  # 上次分析时间戳
        
        # 按设备类型初始化缓存和目录
        if self.monitor_type == "charging_case":
            self.grid_brightness_cache = [[] for _ in range(GRID_COUNT_CHARGING)]
            self._create_root_dirs()
            self._create_restart_subdirs()
        elif self.monitor_type == "hearing_aid":
            self.grid_brightness_cache = [[] for _ in range(GRID_COUNT_HEARING_AID)]
            self._create_root_dirs()
            self._create_restart_subdirs()

    def _create_root_dirs(self):
        """创建根目录（区分设备类型）"""
        try:
            if self.monitor_type == "hearing_aid":
                os.makedirs(HEARING_AID_BRIGHTNESS_ROOT_DIR, exist_ok=True)
            else:  # charging_case
                os.makedirs(CHARGING_BRIGHTNESS_ROOT_DIR, exist_ok=True)
                os.makedirs(CHARGING_ROOT_DIR, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Dir Create Failed", f"Root dir create failed: {str(e)}")

    def _create_restart_subdirs(self):
        """创建本次重启的子目录（区分设备类型）"""
        try:
            if self.monitor_type == "hearing_aid":
                # 助听器：hearing_aid_brightness_log/restart_timestamp/
                restart_dir = os.path.join(HEARING_AID_BRIGHTNESS_ROOT_DIR, self.restart_timestamp)
                os.makedirs(restart_dir, exist_ok=True)
            else:  # charging_case
                # 充电盒亮度日志子目录
                brightness_restart_dir = os.path.join(CHARGING_BRIGHTNESS_ROOT_DIR, self.restart_timestamp)
                # 充电盒状态日志子目录
                charging_restart_dir = os.path.join(CHARGING_ROOT_DIR, self.restart_timestamp)
                os.makedirs(brightness_restart_dir, exist_ok=True)
                os.makedirs(charging_restart_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Dir Create Failed", f"Restart subdir create failed: {str(e)}")

    def _get_10min_segment(self):
        """获取当前10分钟分段ID（YYYYMMDD_HHMM_HHMM）"""
        now = time.localtime()
        year, month, day = now.tm_year, now.tm_mon, now.tm_mday
        hour, minute = now.tm_hour, now.tm_min

        start_minute = (minute // 10) * 10
        end_minute = start_minute + 10
        start_h, end_h = hour, hour
        start_d, end_d = day, day
        
        # 跨小时/跨天处理
        if end_minute >= 60:
            end_minute = 0
            end_h += 1
            if end_h >= 24:
                end_h = 0
                end_d += 1
                if end_d > 31:  # 简易跨月处理
                    end_d = 1
                    end_h = 0

        # 格式化时间字符串（补零）
        date_str = f"{year:04d}{month:02d}{start_d:02d}"
        start_time_str = f"{start_h:02d}{start_minute:02d}"
        end_time_str = f"{end_h:02d}{end_minute:02d}"
        return f"{date_str}_{start_time_str}_{end_time_str}"

    def get_10min_log_filename(self):
        """获取当前10分钟日志文件名（区分设备类型）"""
        segment = self._get_10min_segment()
        if self.monitor_type == "hearing_aid":
            # 助听器路径：hearing_aid_brightness_log/restart_timestamp/10min_segment.json
            restart_dir = os.path.join(HEARING_AID_BRIGHTNESS_ROOT_DIR, self.restart_timestamp)
            return os.path.join(restart_dir, f"{segment}.json")
        elif self.monitor_type == "charging_case":
            # 充电盒亮度日志路径
            restart_dir = os.path.join(CHARGING_BRIGHTNESS_ROOT_DIR, self.restart_timestamp)
            return os.path.join(restart_dir, f"{segment}.json")
        return ""

    def get_charging_status_filename(self):
        """充电盒状态日志文件名（仅充电盒）"""
        if self.monitor_type != "charging_case":
            return ""
        segment = self._get_10min_segment()
        restart_dir = os.path.join(CHARGING_ROOT_DIR, self.restart_timestamp)
        return os.path.join(restart_dir, f"{segment}.json")

    def load_config(self):
        """核心修改2：删除透视参数加载，仅保留边框配置加载"""
        # 加载对应设备的边框配置
        border_file = HEARING_AID_BORDER_DATA if self.monitor_type == "hearing_aid" else CHARGING_CASE_BORDER_DATA
        if os.path.exists(border_file):
            with open(border_file, 'r') as f:
                d = json.load(f)
                self.border_rect = d['contours'][0]['bounding_rect']
        else:
            raise Exception(f"Border config file not found for {self.monitor_type}: {border_file}")

    def init_grid_regions(self):
        """初始化网格区域（区分设备类型，适配原始帧尺寸）"""
        self.grid_regions.clear()
        x, y, w, h = self.border_rect
        index = 0

        if self.monitor_type == "hearing_aid":
            # 助听器：4行14列 = 56格（逻辑不变，基于原始帧边框）
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
            # 充电盒：4行5列 = 20格（逻辑不变，基于原始帧边框）
            gw = w / 5    # 列宽 = 总宽度 / 5
            gh = h / 4    # 行高 = 总高度 / 4
            for row in range(4):
                row_y1 = int(y + row * gh)
                row_y2 = int(y + (row + 1) * gh)
                for col in range(5):
                    col_x1 = int(x + col * gw)
                    col_x2 = int(x + (col + 1) * gw)
                    self.grid_regions.append((col_x1, row_y1, col_x2, row_y2, index))
                    index += 1

    def calculate_grid_bright(self, frame):
        """计算网格亮度（通用逻辑，适配原始帧）"""
        bright_grids = []  # 异常网格（助听器）/亮网格（充电盒）
        grid_brightness = []
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame_gray = cv2.GaussianBlur(frame_gray, (5, 5), 0)

        # 膨胀增强亮斑
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

            # 判定逻辑：助听器（亮=异常）、充电盒（亮=正常亮格）
            if bright_ratio >= BRIGHT_PIXEL_RATIO:
                bright_grids.append(idx)

        # 更新缓存（通用）
        current_time = time.time()
        grid_count = GRID_COUNT_HEARING_AID if self.monitor_type == "hearing_aid" else GRID_COUNT_CHARGING
        for grid_idx in range(grid_count):
            brightness = grid_brightness[grid_idx] if grid_idx < len(grid_brightness) else 0.0
            self.grid_brightness_cache[grid_idx].append((current_time, brightness))

        return bright_grids, grid_brightness, frame_binary

    def clean_expired_cache(self):
        """清理过期缓存（仅保留最近4秒）"""
        current_time = time.time()
        grid_count = GRID_COUNT_HEARING_AID if self.monitor_type == "hearing_aid" else GRID_COUNT_CHARGING
        for grid_idx in range(grid_count):
            self.grid_brightness_cache[grid_idx] = [
                item for item in self.grid_brightness_cache[grid_idx]
                if current_time - item[0] <= CACHE_DURATION
            ]

    def analyze_single_grid_status(self, grid_idx):
        """分析充电盒单个网格状态（仅充电盒）"""
        if self.monitor_type != "charging_case":
            return STATUS_NO_STATUS, "not charging case"
        
        cache = self.grid_brightness_cache[grid_idx]
        if len(cache) < 3:
            return STATUS_NO_STATUS, "insufficient data (startup delay)"
        
        brightness_list = [item[1] for item in cache]
        brightness_mean = np.mean(brightness_list)
        
        # 无状态：亮度低于阈值
        if brightness_mean < BRIGHT_PIXEL_RATIO:
            return STATUS_NO_STATUS, f"brightness below threshold (mean {brightness_mean:.4f} < {BRIGHT_PIXEL_RATIO})"
        
        # 计算波动
        brightness_std = np.std(brightness_list)
        stability_ratio = brightness_std / brightness_mean if brightness_mean > 0 else 1.0

        # 充电完成：亮度稳定
        if stability_ratio < STABILITY_THRESHOLD:
            return STATUS_CHARGED, f"steady light (brightness fluctuation {stability_ratio:.4f} < 5%)"
        
        # 充电中：亮度波动
        x = np.arange(len(brightness_list))
        slope, _ = np.polyfit(x, brightness_list, 1)
        if slope > 0:
            trend = "brightness rising"
        elif slope < 0:
            trend = "brightness falling"
        else:
            trend = "brightness fluctuating"
        
        return STATUS_CHARGING, f"{trend} (fluctuation {stability_ratio:.4f} ≥ 5%)"

    def analyze_charging_case_status(self):
        """分析充电盒状态（仅充电盒）"""
        if self.monitor_type != "charging_case":
            return
        
        # 启动延迟检查
        current_time = time.time()
        if current_time - self.start_time < START_DELAY:
            return
        
        # 清理缓存
        self.clean_expired_cache()
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entries = []
        print(f"\n===== Charging Case Status Analysis [{timestamp}] =====")
        print(f"Restart ID: {self.restart_timestamp}")
        
        # 分析20个网格
        for grid_idx in range(GRID_COUNT_CHARGING):
            status, detail = self.analyze_single_grid_status(grid_idx)
            grid_log_entry = {
                "timestamp": timestamp,
                "restart_timestamp": self.restart_timestamp,
                "grid_id": grid_idx,
                "status": status,
                "detail": detail
            }
            log_entries.append(grid_log_entry)
            print(f"Grid {grid_idx:02d}: {status} - {detail}")
        
        print("=======================================")
        
        # 写入状态日志
        charging_log_file = self.get_charging_status_filename()
        if not charging_log_file:
            return
        
        try:
            existing_logs = []
            if os.path.exists(charging_log_file):
                with open(charging_log_file, 'r', encoding='utf-8') as f:
                    existing_logs = json.load(f)
            existing_logs.extend(log_entries)
            with open(charging_log_file, 'w', encoding='utf-8') as f:
                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showwarning("Status Log Write Failed", f"Charging case status log save failed: {str(e)}")

    def log_change(self, bright_grids, grid_brightness):
        """记录日志（区分设备类型）"""
        # 通用日志基础信息
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_file = self.get_10min_log_filename()
        if not log_file:
            return

        try:
            # 读取现有日志
            logs = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)

            # 按设备类型构建日志条目
            if self.monitor_type == "hearing_aid":
                # 助听器日志：重点记录异常网格（亮格=异常）
                log_entry = {
                    "timestamp": timestamp,
                    "monitor_type": self.monitor_type,
                    "abnormal_grids": bright_grids,  # 异常网格（亮）
                    "grid_brightness": grid_brightness,  # 所有网格亮度
                    "total_abnormal_grids": len(bright_grids),  # 异常网格数
                    "restart_timestamp": self.restart_timestamp,
                    "normal_status": "dark",  # 正常状态：长暗
                    "abnormal_reason": "bright spot detected (fluctuation)"  # 异常原因：亮度波动
                }
            else:  # charging_case
                # 充电盒亮度日志（原有逻辑）
                log_entry = {
                    "timestamp": timestamp,
                    "monitor_type": self.monitor_type,
                    "bright_grids": bright_grids,
                    "grid_brightness": grid_brightness,
                    "total_bright_grids": len(bright_grids),
                    "restart_timestamp": self.restart_timestamp
                }

            # 添加新条目并写入
            logs.append(log_entry)
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)

        except Exception as e:
            msg = f"Hearing aid brightness log save failed: {str(e)}" if self.monitor_type == "hearing_aid" else f"Brightness log save failed: {str(e)}"
            messagebox.showwarning("Log Write Failed", msg)

    def draw_grid_and_bright(self, frame, bright_grids):
        """绘制网格和异常/亮格（通用，适配原始帧）"""
        x, y, w, h = self.border_rect
        # 绘制网格线（区分设备）
        if self.monitor_type == "hearing_aid":
            # 助听器网格线：4行14列
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
            # 充电盒网格线：4行5列
            gw = w / 5
            gh = h / 4
            # 竖线（5列=6条线）
            for i in range(6):
                cv2.line(frame, (int(x + i * gw), y), (int(x + i * gw), y + h), (255, 255, 255), 2)
            # 横线（4行=5条线）
            for i in range(5):
                cv2.line(frame, (x, int(y + i * gh)), (x + w, int(y + i * gh)), (255, 255, 255), 2)

        # 标记异常/亮格（红色覆盖）
        for (x1, y1, x2, y2, idx) in self.grid_regions:
            if idx in bright_grids:
                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
                alpha = 0.3
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
                cv2.putText(frame, str(idx), (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return frame

    def stop_monitor(self):
        """停止监控"""
        self.is_running = False

    def run_monitor(self):
        """监控主循环（核心修改3：移除透视变换，使用原始帧）"""
        try:
            self.load_config()
            self.init_grid_regions()
        except Exception as e:
            messagebox.showerror("Initialization Failed", f"Config load error: {str(e)}")
            return

        # 初始化摄像头
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

        # 记录启动时间
        self.start_time = time.time()

        # 创建监控窗口
        window_title = "Hearing Aid Grid Monitor (Abnormal: Red)" if self.monitor_type == "hearing_aid" else "Charging Case Grid Monitor"
        self.monitor_win = Toplevel(self.root)
        self.monitor_win.title(window_title)
        self.monitor_win.geometry("900x600")
        self.monitor_win.protocol("WM_DELETE_WINDOW", self.stop_monitor)

        # 视频显示区域
        video_label = Label(self.monitor_win)
        video_label.pack(side="top", padx=10, pady=10, fill="both", expand=True)

        # 停止按钮
        stop_btn = Button(self.monitor_win, text="Stop Monitor", bg="#f44336", fg="white",
                          font=("Microsoft YaHei", 12, "bold"), command=self.stop_monitor)
        stop_btn.pack(side="bottom", fill="x", padx=10, pady=10)

        # 主循环
        self.is_running = True
        self.last_analysis_time = time.time()
        
        while self.is_running:
            ret, raw = self.cap.read()
            if not ret:
                break

            # 核心修改4：删除透视变换，直接使用原始帧
            frame = raw

            # 检测亮度/异常
            bright_grids, grid_brightness, _ = self.calculate_grid_bright(frame)
            
            # 清理缓存
            self.clean_expired_cache()

            # 记录日志（助听器/充电盒均执行）
            self.log_change(bright_grids, grid_brightness)
            
            # 充电盒专属：定时状态分析
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
    """启动助听器监控（含异常日志）"""
    monitor = GridMonitor(root, "hearing_aid")
    threading.Thread(target=monitor.run_monitor, daemon=True).start()

def start_charging_case_monitor(root):
    """启动充电盒监控"""
    monitor = GridMonitor(root, "charging_case")
    threading.Thread(target=monitor.run_monitor, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    # 可选择启动对应监控
    # start_hearing_aid_monitor(root)  # 助听器监控
    # start_charging_case_monitor(root)  # 充电盒监控
    root.mainloop()