import cv2
import numpy as np
import json
import tkinter as tk
from tkinter import messagebox
import threading
import time


class CalibrationTool:
    def __init__(self, root):
        self.root = root
        self.left_shrink_percent = 0.0
        self.right_shrink_percent = 0.0
        self.cam_width, self.cam_height = 1920, 1080
        self.is_running = False
        self.params_path = "calibration_params.json"
        self.cap = None
        self.thread_done = False  # 新增：确保线程完全退出的标志

    def draw_grid_lines(self, frame):
        """主线+细线的红色复合网格"""
        h, w = frame.shape[:2]
        RED_MAIN = (0, 0, 255)
        RED_SUB = (0, 0, 100)
        cols, rows, sub_div = 16, 10, 5

        for i in range(cols * sub_div + 1):
            x = int(i * (w / (cols * sub_div)))
            color = RED_MAIN if i % sub_div == 0 else RED_SUB
            thick = 2 if i % sub_div == 0 else 1
            cv2.line(frame, (x, 0), (x, h), color, thick)
        for i in range(rows * sub_div + 1):
            y = int(i * (h / (rows * sub_div)))
            color = RED_MAIN if i % sub_div == 0 else RED_SUB
            thick = 2 if i % sub_div == 0 else 1
            cv2.line(frame, (0, y), (w, y), color, thick)
        cv2.line(frame, (w // 2, 0), (w // 2, h), (0, 255, 0), 2)
        cv2.line(frame, (0, h // 2), (w, h // 2), (0, 255, 0), 2)
        return frame

    def save_params(self):
        try:
            l_pix = (self.left_shrink_percent / 100.0) * self.cam_width
            r_pix = (self.right_shrink_percent / 100.0) * self.cam_width
            src = np.float32([[0, 0], [self.cam_width, 0],
                              [self.cam_width + r_pix, self.cam_height],
                              [-l_pix, self.cam_height]])
            tw = int(self.cam_width - l_pix - r_pix)
            dst = np.float32([[0, 0], [tw, 0], [tw, self.cam_height], [0, self.cam_height]])
            M = cv2.getPerspectiveTransform(src, dst)
            data = {
                "perspective_matrix": M.tolist(),
                "cropped_size": [tw, self.cam_height],
                "left_percent": self.left_shrink_percent,
                "right_percent": self.right_shrink_percent
            }
            with open(self.params_path, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            messagebox.showinfo("成功", "标定参数已成功保存！")
        except Exception as e:
            messagebox.showerror("失败", f"保存出错: {e}")

    def on_close(self):
        """
        关闭逻辑：只发指令，不直接销毁。
        """
        self.is_running = False
        # 启动一个定时检查，直到线程确认关闭了，主窗口才消失
        self.check_thread_and_destroy()

    def check_thread_and_destroy(self):
        if self.thread_done:
            self.root.destroy()
        else:
            # 每100ms检查一次线程是否真的释放了摄像头和窗口
            self.root.after(100, self.check_thread_and_destroy)

    def run_preview(self):
        self.cap = cv2.VideoCapture(1)
        if not self.cap.isOpened(): self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cam_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cam_height)

        self.is_running = True
        win_name = "Calibration_Preview"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, 1000, 600)

        # 核心：将所有 OpenCV 相关的逻辑（包括销毁）全部留在同一个线程
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret: continue

            l_pix = (self.left_shrink_percent / 100.0) * self.cam_width
            r_pix = (self.right_shrink_percent / 100.0) * self.cam_width
            tw = max(int(self.cam_width - l_pix - r_pix), 100)

            src = np.float32([[0, 0], [self.cam_width, 0],
                              [self.cam_width + r_pix, self.cam_height],
                              [-l_pix, self.cam_height]])
            dst = np.float32([[0, 0], [tw, 0], [tw, self.cam_height], [0, self.cam_height]])
            M = cv2.getPerspectiveTransform(src, dst)

            try:
                corrected = cv2.warpPerspective(frame, M, (tw, self.cam_height))
                display_frame = cv2.resize(corrected, (1000, 600))
                display_frame = self.draw_grid_lines(display_frame)
                cv2.imshow(win_name, display_frame)
            except:
                pass

            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.is_running = False

        # --- 退出时的资源释放 (在子线程内完成) ---
        print("正在后台释放资源...")
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        # 通知主线程可以安全销毁窗口了
        self.thread_done = True


def start_calibration():
    sub_root = tk.Toplevel()
    sub_root.title("标定工具 - 防卡死版")
    sub_root.geometry("500x380")

    tool = CalibrationTool(sub_root)
    # 拦截关闭协议
    sub_root.protocol("WM_DELETE_WINDOW", tool.on_close)

    tk.Scale(sub_root, from_=0, to=20, resolution=0.1, label="左侧收缩 (%)", orient="horizontal", length=450,
             command=lambda v: setattr(tool, 'left_shrink_percent', float(v))).pack(pady=10)
    tk.Scale(sub_root, from_=0, to=20, resolution=0.1, label="右侧收缩 (%)", orient="horizontal", length=450,
             command=lambda v: setattr(tool, 'right_shrink_percent', float(v))).pack(pady=10)

    btn_frame = tk.Frame(sub_root)
    btn_frame.pack(pady=20)
    tk.Button(btn_frame, text=" 💾 保存参数 ", bg="#4CAF50", fg="white",
              font=("微软雅黑", 10, "bold"), command=tool.save_params).grid(row=0, column=0, padx=20)
    tk.Button(btn_frame, text=" ❌ 退出 ", bg="#f44336", fg="white",
              font=("微软雅黑", 10, "bold"), command=tool.on_close).grid(row=0, column=1, padx=20)

    threading.Thread(target=tool.run_preview, daemon=True).start()