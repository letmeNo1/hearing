import time
import cv2
import numpy as np
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

# ========== 配置项（统一管理，便于修改） ==========
CURRENT_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HEARING_AID_BORDER_DATA = os.path.join(CURRENT_SCRIPT_DIR, "hearing_aid_border.json")
CHARGING_CASE_BORDER_DATA = os.path.join(CURRENT_SCRIPT_DIR, "charging_case_border.json")
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 540
MIN_CONTOUR_AREA = 5000  # 最小轮廓面积（过滤小噪点）
AREA_RATIO_LOW = 30.0     # 助听器边框面积占比下限
AREA_RATIO_HIGH = 32.0    # 助听器边框面积占比上限

class DetectionSystem:
    def __init__(self, root):
        self.root = root  # 主窗口对象
        self.is_running = False
        self.preview_win = None
        self.cap = None
        self.video_label = None  # 保存Label引用，便于检查
        self.gui_lock = threading.Lock()  # 加锁保护GUI操作
        self.thread = None  # 保存线程引用，避免线程泄露

    def draw_hearing_aid(self, img, r):
        """绘制助听器网格（4行14列）"""
        if r is None or len(r) != 4 or r[2] <= 0 or r[3] <= 0:
            return img
        x, y, w, h = r
        y_off = int(h * 0.05)
        ys, ye, nh = y + y_off, y + h - y_off, h - 2 * y_off
        gw, xs = w / 14, int(x + (w / 14) / 2)
        
        line_color = (255, 0, 255)  # 品红
        line_width = 2
        # 绘制竖线（14列 → 14条线）
        for i in range(14):
            cx = int(xs + i * gw)
            cv2.line(img, (cx, ys), (cx, ye), line_color, line_width)
        # 绘制横线（4行 → 5条线）
        for i in range(5):
            cy = int(ys + i * (nh / 4))
            cv2.line(img, (xs, cy), (int(xs + 13 * gw), cy), line_color, line_width)
        return img

    def draw_charging_case(self, img, r):
        """修复充电盒网格绘制（4行5列）"""
        if r is None or len(r) != 4 or r[2] <= 0 or r[3] <= 0:
            return img
        x, y, w, h = r
        gw = w / 5  # 5列 → 每列宽度
        gh = h / 4  # 4行 → 每行高度
        
        line_color = (0, 255, 255)  # 黄色
        line_width = 2
        # 绘制竖线（5列 → 6条线）
        for i in range(6):
            cv2.line(img, (int(x + i * gw), y), (int(x + i * gw), y + h), line_color, line_width)
        # 绘制横线（4行 → 5条线）
        for i in range(5):
            cy = int(y + i * gh)
            cv2.line(img, (x, cy), (x + w, cy), line_color, line_width)
        return img

    def clean_resources(self):
        """统一清理资源（加锁，确保线程安全）"""
        with self.gui_lock:
            self.is_running = False
        
        # 等待工作线程结束（避免强制终止导致资源泄露）
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        
        # 释放摄像头（加锁保护）
        with self.gui_lock:
            if self.cap is not None and self.cap.isOpened():
                self.cap.release()
                self.cap = None
            
            # 销毁预览窗口（先检查是否存在，避免报错）
            if self.preview_win is not None:
                try:
                    self.preview_win.destroy()
                except tk.TclError:
                    pass
                self.preview_win = None
            
            # 清空Label引用
            self.video_label = None
            self.thread = None  # 清空线程引用

    def update_video_frame(self, img_tk):
        """主线程更新视频帧（避免子线程直接操作GUI）"""
        with self.gui_lock:
            if self.video_label is not None and self.preview_win is not None:
                try:
                    self.video_label.config(image=img_tk)
                    self.video_label.image = img_tk  # 保持引用，防止GC回收
                except tk.TclError:
                    pass  # 窗口已销毁，忽略

    def worker(self, mode):
        """工作线程：处理摄像头读取、绘制、标定逻辑"""
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
                # 主线程弹提示（线程安全）
                self.root.after(0, lambda: messagebox.showinfo(
                    "摄像头切换", 
                    "摄像头1不可用，已自动切换到摄像头0"
                ))
        
        if not camera_ok:
            self.root.after(0, lambda: messagebox.showerror(
                "摄像头错误", 
                "所有摄像头均不可用！请检查摄像头连接或权限"
            ))
            self.clean_resources()
            return

        # 1.2 预览模式：检查边框文件（核心错误，直接终止）
        border_path = ""
        if mode in ["hearing_aid", "charging_case"]:
            border_path = HEARING_AID_BORDER_DATA if mode == "hearing_aid" else CHARGING_CASE_BORDER_DATA
            if not os.path.exists(border_path):
                tip = "助听器" if mode == "hearing_aid" else "充电盒"
                self.root.after(0, lambda: messagebox.showerror(
                    "边框配置缺失", 
                    f"未找到{tip}边框配置文件：\n{border_path}\n请先执行【自动标定】功能生成配置"
                ))
                self.clean_resources()
                return

        # ========== 步骤2：所有前置检查通过，创建预览窗口 ==========
        with self.gui_lock:
            self.is_running = True
        detection_success = False

        # 创建预览窗口（主线程操作，避免子线程创建窗口）
        def create_preview_win():
            self.preview_win = tk.Toplevel(self.root)
            self.preview_win.title(f"实时预览 - {mode}模式")
            self.preview_win.geometry(f"{PREVIEW_WIDTH+20}x{PREVIEW_HEIGHT+60}")  # 预留按钮空间
            self.preview_win.protocol("WM_DELETE_WINDOW", self.clean_resources)  # 关闭窗口时清理资源

            # 视频显示Label
            self.video_label = tk.Label(self.preview_win)
            self.video_label.pack(padx=10, pady=10)

            # 底部关闭按钮
            btn_text = "停止监测" if mode == "detect" else "关闭预览"
            close_btn = tk.Button(
                self.preview_win, 
                text=btn_text, 
                bg="#f44336", 
                fg="white",
                font=("微软雅黑", 12, "bold"), 
                pady=8, 
                command=self.clean_resources
            )
            close_btn.pack(fill=tk.X, padx=10, pady=10)

        # 确保窗口在主线程创建（线程安全）
        self.root.after(0, create_preview_win)
        time.sleep(0.2)  # 等待窗口创建完成（避免后续操作提前执行）

        # 设置摄像头参数（提升画面质量）
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, 30)  # 设置帧率

        # ========== 步骤3：帧循环（仅无前置错误时执行） ==========
        while True:
            # 先检查是否继续运行（加锁）
            with self.gui_lock:
                if not self.is_running:
                    break

            ret, raw = self.cap.read()
            # 摄像头读取失败 → 清理资源并终止
            if not ret: 
                self.root.after(0, lambda: messagebox.showerror(
                    "摄像头错误", 
                    "无法读取摄像头画面！请检查摄像头是否被占用"
                ))
                self.clean_resources()
                break

            # 直接使用原始帧（移除透视变换）
            frame = raw.copy()

            if mode == "detect":
                # 检测模式：自动标定助听器边框
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # 高斯模糊+自适应二值化（提升轮廓检测准确性）
                blur = cv2.GaussianBlur(gray, (7, 7), 0)
                binary = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                               cv2.THRESH_BINARY_INV, 11, 2)
                # 查找外部轮廓（过滤内部小轮廓）
                cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                target = None
                
                frame_area = frame.shape[1] * frame.shape[0]  # 画面总面积（宽×高）
                for c in cnts:
                    # 过滤小轮廓（减少噪点干扰）
                    if cv2.contourArea(c) < MIN_CONTOUR_AREA:
                        continue
                    x, y, w, h = cv2.boundingRect(c)
                    # 计算轮廓面积占画面的比例
                    area_ratio = (w * h / frame_area) * 100
                    # 匹配目标面积占比（30%-32%）
                    if AREA_RATIO_LOW <= area_ratio <= AREA_RATIO_HIGH:
                        target = (x, y, w, h)
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)  # 绿色框标注目标
                        break  # 找到目标后退出循环
                
                # 绘制助听器网格（如果找到目标）
                frame = self.draw_hearing_aid(frame, target)
                
                # 标定成功：保存配置并退出
                if target is not None:
                    try:
                        with open(HEARING_AID_BORDER_DATA, "w", encoding="utf-8") as f:
                            json.dump({"contours": [{"bounding_rect": target}]}, f, indent=2)
                        detection_success = True
                        self.root.after(0, lambda: messagebox.showinfo(
                            "标定成功", 
                            f"助听器边框自动标定完成！\n配置已保存到：\n{HEARING_AID_BORDER_DATA}"
                        ))
                    except Exception as e:
                        self.root.after(0, lambda: messagebox.showerror(
                            "保存失败", 
                            f"配置文件保存失败：\n{str(e)}"
                        ))
                    self.clean_resources()
                    break
            else:
                # 预览模式：解析边框文件并绘制网格
                try:
                    with open(border_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        contours = data.get("contours", [])
                        if contours:
                            r = contours[0].get("bounding_rect")
                            if mode == "hearing_aid":
                                frame = self.draw_hearing_aid(frame, r)
                            else:
                                frame = self.draw_charging_case(frame, r)
                except json.JSONDecodeError:
                    self.root.after(0, lambda: messagebox.showerror(
                        "配置解析错误", 
                        f"边框文件格式错误：\n{border_path}\n请重新执行标定"
                    ))
                    self.clean_resources()
                    break
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror(
                        "配置读取错误", 
                        f"边框文件读取失败：\n{border_path}\n错误信息：{str(e)}"
                    ))
                    self.clean_resources()
                    break

            # 转换图像格式（适配Tkinter显示）
            img_show = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_HEIGHT))
            img_rgb = cv2.cvtColor(img_show, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            img_tk = ImageTk.PhotoImage(image=img_pil)
            
            # 主线程更新视频帧（线程安全）
            self.root.after(0, self.update_video_frame, img_tk)

            # 键盘退出（按q键退出，降低CPU占用）
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.clean_resources()
                break

        # ========== 步骤4：最终清理 ==========
        self.clean_resources()
        # 标定失败提示
        if mode == "detect" and not detection_success and self.is_running is False:
            self.root.after(0, lambda: messagebox.showwarning(
                "标定失败", 
                "未检测到符合条件的助听器边框！\n请调整摄像头角度或确保目标在画面中"
            ))

    def start(self, mode):
        """启动检测/预览（对外暴露的安全入口）"""
        # 先停止已有任务
        self.clean_resources()
        # 启动新线程（避免阻塞主线程）
        self.thread = threading.Thread(target=self.worker, args=(mode,), daemon=True)
        self.thread.start()

# ========== 测试入口（可直接运行） ==========
if __name__ == "__main__":
    root = tk.Tk()
    root.title("检测系统主界面")
    root.geometry("400x200")

    # 创建检测系统实例
    detector = DetectionSystem(root)

    # 按钮布局
    frame_btn = tk.Frame(root)
    frame_btn.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

    # 自动标定按钮
    btn_detect = tk.Button(
        frame_btn, 
        text="助听器自动标定", 
        font=("微软雅黑", 12),
        command=lambda: detector.start("detect"),
        width=20, height=2
    )
    btn_detect.grid(row=0, column=0, padx=10, pady=10)

    # 助听器预览按钮
    btn_hearing = tk.Button(
        frame_btn, 
        text="助听器网格预览", 
        font=("微软雅黑", 12),
        command=lambda: detector.start("hearing_aid"),
        width=20, height=2
    )
    btn_hearing.grid(row=0, column=1, padx=10, pady=10)

    # 充电盒预览按钮
    btn_charging = tk.Button(
        frame_btn, 
        text="充电盒网格预览", 
        font=("微软雅黑", 12),
        command=lambda: detector.start("charging_case"),
        width=20, height=2
    )
    btn_charging.grid(row=1, column=0, columnspan=2, padx=10, pady=10)

    # 主循环
    root.mainloop()