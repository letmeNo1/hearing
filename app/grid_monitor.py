import cv2
import numpy as np
import json
import os
import time
import threading
from tkinter import Toplevel, Label, Button, Text, END, Scrollbar, VERTICAL, RIGHT, Y, font
import tkinter as tk
import tkinter.messagebox as messagebox
from PIL import Image, ImageTk

# 配置常量
PARAMS_FILE = "calibration_params.json"
HEARING_AID_BORDER_DATA = "hearing_aid_border.json"
CHARGING_CASE_BORDER_DATA = "charging_case_border.json"
LOG_FILE = "brightness_log.json"  # JSON格式日志
CAM_WIDTH, CAM_HEIGHT = 1920, 1080

# 亮度检测配置
BRIGHT_THRESHOLD = 35
BRIGHT_PIXEL_RATIO = 0.001
DILATE_KERNEL_SIZE = (5, 5)

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
        self.log_text = None

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
            gw = w / 9
            gh = h / 2
            for row in range(2):
                row_y1 = int(y + row * gh)
                row_y2 = int(y + (row + 1) * gh)
                for col in range(9):
                    col_x1 = int(x + col * gw)
                    col_x2 = int(x + (col + 1) * gw)
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
            grid_dilated = frame_binary[y1:y2, x1:x2]  # 修正变量名错误
            total_pixels = grid_dilated.size
            if total_pixels == 0:
                grid_brightness.append(0)
                continue

            bright_pixels = np.count_nonzero(grid_dilated)
            bright_ratio = bright_pixels / total_pixels
            grid_brightness.append(bright_ratio)

            if bright_ratio >= BRIGHT_PIXEL_RATIO:
                bright_grids.append(idx)

        return bright_grids, grid_brightness, frame_binary

    def log_change(self, bright_grids, grid_brightness):
        if not bright_grids:
            return

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entry = {
            "timestamp": timestamp,
            "monitor_type": self.monitor_type,
            "bright_grids": bright_grids,
            "grid_brightness": grid_brightness,
            "total_bright_grids": len(bright_grids)
        }

        log_msg = f"[{timestamp}] 检测到亮光的网格索引: {bright_grids}\n"

        # 写入JSON日志（追加模式）
        try:
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            else:
                logs = []

            logs.append(log_entry)

            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showwarning("日志写入失败", f"无法保存日志：{str(e)}")

        # 更新UI日志
        if self.log_text:
            self.root.after(0, lambda: self.log_text.insert(END, log_msg))
            self.root.after(0, lambda: self.log_text.see(END))

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
            gw = w / 9
            gh = h / 2
            for i in range(10):
                cv2.line(frame, (int(x + i * gw), y), (int(x + i * gw), y + h), (255, 255, 255), 2)
            for i in range(3):
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

        # 创建监控窗口
        self.monitor_win = Toplevel(self.root)
        self.monitor_win.title(f"{('助听器' if self.monitor_type == 'hearing_aid' else '充电盒')}网格监控")
        self.monitor_win.geometry("1200x700")
        self.monitor_win.protocol("WM_DELETE_WINDOW", self.stop_monitor)

        # 视频显示区域
        video_label = Label(self.monitor_win)
        video_label.pack(side="left", padx=10, pady=10)

        # 日志显示区域
        log_frame = tk.Frame(self.monitor_win)
        log_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        Label(log_frame, text="亮光检测日志", font=("微软雅黑", 12, "bold")).pack()
        
        scroll = Scrollbar(log_frame, orient=VERTICAL)
        self.log_text = Text(log_frame, yscrollcommand=scroll.set, font=("Consolas", 10), wrap="none")
        scroll.config(command=self.log_text.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.log_text.pack(fill="both", expand=True)

        # 停止按钮
        stop_btn = Button(self.monitor_win, text="停止监控", bg="#f44336", fg="white",
                          font=("微软雅黑", 12, "bold"), command=self.stop_monitor)
        stop_btn.pack(side="bottom", fill="x", padx=10, pady=10)

        # 监控主循环
        self.is_running = True
        while self.is_running:
            ret, raw = self.cap.read()
            if not ret:
                break

            # 透视变换校正
            frame = cv2.warpPerspective(raw, self.M, self.size) if self.M is not None else raw

            # 检测亮光
            bright_grids, grid_brightness, _ = self.calculate_grid_bright(frame)
            # 记录日志
            self.log_change(bright_grids, grid_brightness)
            # 绘制标注
            frame = self.draw_grid_and_bright(frame, bright_grids)

            # 转换为Tkinter显示格式
            frame_show = cv2.resize(frame, (800, 450))
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
    """启动助听器网格监控"""
    monitor = GridMonitor(root, "hearing_aid")
    threading.Thread(target=monitor.run_monitor, daemon=True).start()

def start_charging_case_monitor(root):
    """启动充电盒网格监控"""
    monitor = GridMonitor(root, "charging_case")
    threading.Thread(target=monitor.run_monitor, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    # 测试充电盒监控（可切换为start_hearing_aid_monitor）
    start_charging_case_monitor(root)
    root.mainloop()