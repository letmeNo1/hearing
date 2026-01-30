import time
import cv2
import numpy as np
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# ========== 仅保留边框配置文件路径（移除透视变换配置文件） ==========
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HEARING_AID_BORDER_DATA = os.path.join(CURRENT_SCRIPT_DIR, "hearing_aid_border.json")
CHARGING_CASE_BORDER_DATA = os.path.join(CURRENT_SCRIPT_DIR, "charging_case_border.json")


class DetectionSystem:
    def __init__(self, root):
        self.root = root  # 主窗口对象
        self.is_running = False
        self.preview_win = None
        self.cap = None
        self.video_label = None  # 保存Label引用，便于检查
        self.gui_lock = threading.Lock()  # 加锁保护GUI操作

    def draw_hearing_aid(self, img, r):
        """绘制助听器网格（4行14列）"""
        if r is None or len(r) != 4 or r[2] <= 0 or r[3] <= 0:
            return img
        x, y, w, h = r
        y_off = int(h * 0.05)
        ys, ye, nh = y + y_off, y + h - y_off, h - 2 * y_off
        gw, xs = w / 14, int(x + (w / 14) / 2)
        
        line_color = (255, 0, 255)
        line_width = 2
        for i in range(14):
            cx = int(xs + i * gw)
            cv2.line(img, (cx, ys), (cx, ye), line_color, line_width)
        for i in range(5):
            cy = int(ys + i * (nh / 4))
            cv2.line(img, (xs, cy), (int(xs + 13 * gw), cy), line_color, line_width)
        return img

    def draw_charging_case(self, img, r):
        """修复充电盒网格绘制（4行5列）"""
        if r is None or len(r) != 4 or r[2] <= 0 or r[3] <= 0:
            return img
        x, y, w, h = r
        gw = w / 5
        gh = h / 4
        
        line_color = (0, 255, 255)
        line_width = 2
        for i in range(6):
            cv2.line(img, (int(x + i * gw), y), (int(x + i * gw), y + h), line_color, line_width)
        for i in range(5):
            cv2.line(img, (x, int(y + i * gh)), (x + w, int(y + i * gh)), line_color, line_width)
        return img

    def clean_resources(self):
        """统一清理资源（加锁，确保线程安全）"""
        with self.gui_lock:
            self.is_running = False
            # 释放摄像头
            if self.cap is not None and self.cap.isOpened():
                self.cap.release()
                self.cap = None
            # 销毁窗口（先检查是否存在）
            if self.preview_win is not None:
                try:
                    self.preview_win.destroy()
                except:
                    pass
                self.preview_win = None
            # 清空Label引用
            self.video_label = None

    def update_video_frame(self, img_tk):
        """主线程更新视频帧（避免子线程直接操作GUI）"""
        with self.gui_lock:
            if self.video_label is not None and self.preview_win is not None:
                try:
                    self.video_label.config(image=img_tk)
                    self.video_label.image = img_tk  # 保持引用
                except:
                    pass  # 窗口已销毁，忽略

    def worker(self, mode):
        # ========== 步骤1：前置检查（所有关键错误先检查，不创建窗口） ==========
        # 1.1 检查摄像头（核心错误，直接终止）
        self.cap = cv2.VideoCapture(1)
        camera_ok = False
        if self.cap.isOpened():
            camera_ok = True
        else:
            self.cap = cv2.VideoCapture(0)
            if self.cap.isOpened():
                camera_ok = True
                # 主线程弹提示
                self.root.after(0, lambda: messagebox.showinfo("摄像头切换", "摄像头1不可用，已切换到摄像头0"))
        
        if not camera_ok:
            self.root.after(0, lambda: messagebox.showerror("摄像头错误", "所有摄像头均不可用！"))
            self.clean_resources()
            return

        # 1.2 预览模式：检查边框文件（核心错误，直接终止）
        border_path = ""
        if mode in ["hearing_aid", "white"]:
            border_path = HEARING_AID_BORDER_DATA if mode == "hearing_aid" else CHARGING_CASE_BORDER_DATA
            if not os.path.exists(border_path):
                tip = "助听器" if mode == "hearing_aid" else "充电盒"
                # 主线程弹提示
                self.root.after(0, lambda: messagebox.showerror(
                    "边框配置缺失", 
                    f"未找到{tip}边框配置文件：\n{border_path}\n请手动执行对应校准功能生成配置"
                ))
                self.clean_resources()
                return

        # ========== 步骤2：所有前置检查通过，才创建预览窗口 ==========
        with self.gui_lock:
            self.is_running = True
        detection_success = False

        # 创建预览窗口（主线程操作，避免子线程创建窗口）
        def create_preview_win():
            self.preview_win = tk.Toplevel(self.root)
            self.preview_win.title(f"系统预览 - {mode}")
            self.preview_win.protocol("WM_DELETE_WINDOW", self.clean_resources)

            # 视频显示Label
            self.video_label = tk.Label(self.preview_win)
            self.video_label.pack()

            # 底部关闭按钮
            btn_text = "停止监测" if mode == "detect" else "关闭预览"
            close_btn = tk.Button(self.preview_win, text=btn_text, bg="#f44336", fg="white",
                                  font=("微软雅黑", 12, "bold"), pady=8, command=self.clean_resources)
            close_btn.pack(fill=tk.X)

        # 确保窗口在主线程创建
        self.root.after(0, create_preview_win)
        # 等待窗口创建完成（避免后续操作提前执行）
        time.sleep(0.1)

        # 设置摄像头参数
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        # ========== 步骤3：帧循环（仅无前置错误时执行） ==========
        while True:
            # 先检查是否继续运行（加锁）
            with self.gui_lock:
                if not self.is_running:
                    break

            ret, raw = self.cap.read()
            # 摄像头读取失败 → 清理资源并终止
            if not ret: 
                self.root.after(0, lambda: messagebox.showerror("摄像头错误", "无法读取摄像头画面！"))
                self.clean_resources()
                break

            # ========== 核心修改：移除透视变换，直接使用原始帧 ==========
            frame = raw

            if mode == "detect":
                # 检测模式：自动标定助听器边框（适配原始帧尺寸）
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                binary = cv2.adaptiveThreshold(cv2.GaussianBlur(gray, (7, 7), 0), 255, 1, 1, 11, 2)
                cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                target = None
                # 适配原始帧尺寸计算面积占比（1920*1080）
                frame_area = frame.shape[1] * frame.shape[0]  # width * height
                for c in cnts:
                    if cv2.contourArea(c) < 5000:
                        continue
                    x, y, w, h = cv2.boundingRect(c)
                    area_ratio = (w * h / frame_area) * 100
                    if 30.0 <= area_ratio <= 32.0:
                        target = (x, y, w, h)
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                frame = self.draw_hearing_aid(frame, target)
                if target:
                    with open(HEARING_AID_BORDER_DATA, "w") as f:
                        json.dump({"contours": [{"bounding_rect": target}]}, f)
                    detection_success = True
                    self.clean_resources()
                    # 主线程弹成功提示
                    self.root.after(0, lambda: messagebox.showinfo(
                        "检测结果", 
                        f"目标实时监测成功！\n参数已自动保存到：\n{HEARING_AID_BORDER_DATA}"
                    ))
                    break
            else:
                # 预览模式：解析边框文件（出错则清理资源）
                try:
                    with open(border_path, "r") as f:
                        data = json.load(f)
                        for c in data.get("contours", []):
                            r = c.get("bounding_rect")
                            frame = self.draw_hearing_aid(frame, r) if mode == "hearing_aid" else self.draw_charging_case(frame, r)
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror(
                        "配置解析错误", 
                        f"边框文件解析失败：\n{border_path}\n错误信息：{str(e)}\n请手动重新校准或修改配置文件"
                    ))
                    self.clean_resources()
                    break

            # 转换图像并通过主线程更新
            img_show = cv2.resize(frame, (960, 540))
            img_rgb = cv2.cvtColor(img_show, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            img_tk = ImageTk.PhotoImage(image=img_pil)
            
            # 主线程更新Label
            self.root.after(0, self.update_video_frame, img_tk)

            # 键盘退出（短延时，降低CPU占用）
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.clean_resources()
                break

        # ========== 步骤4：最终清理 ==========
        self.clean_resources()