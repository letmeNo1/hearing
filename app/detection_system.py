import cv2
import numpy as np
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# 配置常量
PARAMS_FILE = "calibration_params.json"
PINK_DATA = "contour_result.json"
WHITE_DATA = "black_border.json"


class DetectionSystem:
    def __init__(self, root):
        self.root = root  # 接收来自 main.py 的主窗口对象
        self.M = None
        self.size = (1920, 1080)
        self.is_running = False
        self.preview_win = None

    def load_config(self):
        if os.path.exists(PARAMS_FILE):
            with open(PARAMS_FILE, 'r') as f:
                d = json.load(f)
                self.M = np.array(d['perspective_matrix'])
                self.size = tuple(d['cropped_size'])

    def draw_pink(self, img, r):
        if r is None: return img
        x, y, w, h = r
        y_off = int(h * 0.05)
        ys, ye, nh = y + y_off, y + h - y_off, h - 2 * y_off
        gw, xs = w / 14, int(x + (w / 14) / 2)
        for i in range(14):
            cx = int(xs + i * gw)
            cv2.line(img, (cx, ys), (cx, ye), (255, 0, 255), 2)
        for i in range(5):
            cy = int(ys + i * (nh / 4))
            cv2.line(img, (xs, cy), (int(xs + 13 * gw), cy), (255, 0, 255), 2)
        return img

    def draw_white(self, img, r):
        if r is None: return img
        x, y, w, h = r
        gw, gh = w / 5, h / 2
        for i in range(6): cv2.line(img, (int(x + i * gw), y), (int(x + i * gw), y + h), (255, 255, 255), 2)
        for i in range(3): cv2.line(img, (x, int(y + i * gh)), (x + w, int(y + i * gh)), (255, 255, 255), 2)
        return img

    def stop_preview(self):
        """关闭按钮触发的操作"""
        self.is_running = False

    def worker(self, mode):
        self.load_config()
        cap = cv2.VideoCapture(1)
        if not cap.isOpened(): cap = cv2.VideoCapture(0)
        cap.set(3, 1920)
        cap.set(4, 1080)
        self.is_running = True
        detection_success = False

        # --- 在主线程中创建 Toplevel 窗口 ---
        # 注意：Tkinter 窗口操作建议在 Thread 中通过 root.after 或直接创建（如果是 Toplevel 通常还行）
        self.preview_win = tk.Toplevel(self.root)
        self.preview_win.title(f"系统预览 - {mode}")
        self.preview_win.protocol("WM_DELETE_WINDOW", self.stop_preview)

        # 视频显示区域
        video_label = tk.Label(self.preview_win)
        video_label.pack()

        # 底部关闭按钮
        btn_text = "停止监测" if mode == "detect" else "关闭预览"
        close_btn = tk.Button(self.preview_win, text=btn_text, bg="#f44336", fg="white",
                              font=("微软雅黑", 12, "bold"), pady=8, command=self.stop_preview)
        close_btn.pack(fill=tk.X)

        while self.is_running:
            ret, raw = cap.read()
            if not ret: break

            frame = cv2.warpPerspective(raw, self.M, self.size) if self.M is not None else raw

            if mode == "detect":
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                binary = cv2.adaptiveThreshold(cv2.GaussianBlur(gray, (7, 7), 0), 255, 1, 1, 11, 2)
                cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                target = None
                for c in cnts:
                    if cv2.contourArea(c) < 5000: continue
                    x, y, w, h = cv2.boundingRect(c)
                    if 30.0 <= (w * h / (self.size[0] * self.size[1]) * 100) <= 35.0:
                        target = (x, y, w, h)
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                frame = self.draw_pink(frame, target)
                if target:
                    with open(PINK_DATA, "w") as f:
                        json.dump({"contours": [{"bounding_rect": target}]}, f)
                    detection_success = True
                    self.is_running = False  # 自动停止
            else:
                path = PINK_DATA if mode == "pink" else WHITE_DATA
                if os.path.exists(path):
                    with open(path, "r") as f:
                        for c in json.load(f).get("contours", []):
                            r = c["bounding_rect"]
                            frame = self.draw_pink(frame, r) if mode == "pink" else self.draw_white(frame, r)

            # --- 转换图像格式以供 Tkinter Label 显示 ---
            img_show = cv2.resize(frame, (960, 540))
            img_rgb = cv2.cvtColor(img_show, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            img_tk = ImageTk.PhotoImage(image=img_pil)

            video_label.config(image=img_tk)
            video_label.image = img_tk  # 必须保持引用

            if cv2.waitKey(1) & 0xFF == ord('q'): break

        # 释放资源
        cap.release()
        self.preview_win.destroy()

        if detection_success:
            # 弹窗提示成功
            messagebox.showinfo("检测结果", "目标实时监测成功！\n参数已自动保存并更新。")