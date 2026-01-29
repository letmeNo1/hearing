import cv2
import numpy as np
import json
import tkinter as tk
from tkinter import ttk, messagebox
import os
import threading

# 全局变量
cap = None
cam_width = 1920
cam_height = 1080
cam_total_area = cam_width * cam_height
is_previewing = False
is_detecting = False
is_previewing_white = False

# 显示缩放配置
DISPLAY_SCALE = 0.5
display_width = int(cam_width * DISPLAY_SCALE)
display_height = int(cam_height * DISPLAY_SCALE)

# ===================== 网格配置 =====================
HEARING_AID_GRID_ROWS = 4
HEARING_AID_GRID_COLS_CALC = 14
HEARING_AID_GRID_COLS_DISPLAY = 13
HEARING_AID_GRID_COLOR = (255, 0, 0)
HEARING_AID_GRID_THICKNESS = 2

WHITE_GRID_ROWS = 2
WHITE_GRID_COLS = 5
WHITE_BORDER_COLOR = (255, 255, 255)
WHITE_BORDER_THICKNESS = 5
WHITE_GRID_COLOR = (255, 0, 0)
WHITE_GRID_THICKNESS = 2

WHITE_BORDER_JSON_PATH = "charging_case_border.json"


# ===================== 核心函数：移除畸变逻辑 =====================

def init_camera():
    """初始化摄像头，强制原始 1920x1080 尺寸"""
    global cap
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        messagebox.showerror("错误", "❌ 无法打开摄像头！")
        return False
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    return True


def draw_HEARING_AID_grid(frame, target_rect):
    """粉色框网格：14等分计算，显示13列，4行，保留偏移"""
    if target_rect is None: return frame
    frame_copy = frame.copy()
    x, y, w, h = target_rect
    grid_w = w / HEARING_AID_GRID_COLS_CALC
    grid_h = h / HEARING_AID_GRID_ROWS
    x_new = int(x + grid_w / 2)

    # 绘制网格
    for col in range(HEARING_AID_GRID_COLS_DISPLAY + 1):
        curr_x = int(x_new + col * grid_w)
        cv2.line(frame_copy, (curr_x, y), (curr_x, y + h), HEARING_AID_GRID_COLOR, HEARING_AID_GRID_THICKNESS)
    for row in range(HEARING_AID_GRID_ROWS + 1):
        curr_y = int(y + row * grid_h)
        line_end = int(x_new + HEARING_AID_GRID_COLS_DISPLAY * grid_w)
        cv2.line(frame_copy, (x_new, curr_y), (line_end, curr_y), HEARING_AID_GRID_COLOR, HEARING_AID_GRID_THICKNESS)
    return frame_copy


def draw_white_grid(frame, target_rect):
    """白色框网格：5列2行，无偏移"""
    if target_rect is None: return frame
    frame_copy = frame.copy()
    x, y, w, h = target_rect
    grid_w, grid_h = w / WHITE_GRID_COLS, h / WHITE_GRID_ROWS
    for i in range(WHITE_GRID_COLS + 1):
        cx = int(x + i * grid_w)
        cv2.line(frame_copy, (cx, y), (cx, y + h), WHITE_GRID_COLOR, WHITE_GRID_THICKNESS)
    for i in range(WHITE_GRID_ROWS + 1):
        cy = int(y + i * grid_h)
        cv2.line(frame_copy, (x, cy), (x + w, cy), WHITE_GRID_COLOR, WHITE_GRID_THICKNESS)
    return frame_copy


# ===================== 检测与预览逻辑 =====================

def detect_contours_by_ratio(target_ratio_range):
    global cap, is_detecting
    if not init_camera(): return
    is_detecting = True
    print("\n🔍 开始检测原始画面（无畸变校正）")

    while is_detecting:
        ret, frame = cap.read()
        if not ret: continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_copy = frame.copy()
        target_rect = None
        current_detected = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 2000: continue
            x, y, w, h = cv2.boundingRect(cnt)
            rect_ratio = ((w * h) / cam_total_area) * 100

            if target_ratio_range[0] <= rect_ratio <= target_ratio_range[1]:
                box = np.int32(cv2.boxPoints(cv2.minAreaRect(cnt)))
                current_detected.append({
                    "rect_ratio": round(rect_ratio, 2),
                    "bounding_box_coordinates": box.tolist(),
                    "bounding_rect": (x, y, w, h)
                })
                cv2.drawContours(frame_copy, [box], 0, (0, 255, 0), 4)
                target_rect = (x, y, w, h)

        frame_final = draw_HEARING_AID_grid(frame_copy, target_rect)
        cv2.imshow("Detection - Original Frame", cv2.resize(frame_final, (display_width, display_height)))

        if (cv2.waitKey(1) & 0xFF == ord('q')) or current_detected:
            if current_detected:
                with open("hearing_aid_border.json", "w") as f:
                    json.dump({"contours": current_detected}, f, indent=4)
            break

    is_detecting = False
    cap.release()
    cv2.destroyAllWindows()


def preview_saved_contours(grid_type="hearing_aid"):
    global is_previewing, is_previewing_white, cap
    json_path = "hearing_aid_border.json" if grid_type == "hearing_aid" else WHITE_BORDER_JSON_PATH
    if not os.path.exists(json_path):
        messagebox.showerror("错误", f"未找到 {json_path}")
        return
    if not init_camera(): return

    if grid_type == "hearing_aid":
        is_previewing = True
    else:
        is_previewing_white = True

    while is_previewing or is_previewing_white:
        ret, frame = cap.read()
        if not ret: break
        with open(json_path, "r") as f:
            data = json.load(f)

        for c in data.get("contours", []):
            rect = c["bounding_rect"]
            frame = draw_HEARING_AID_grid(frame, rect) if grid_type == "hearing_aid" else draw_white_grid(frame, rect)

        cv2.imshow(f"Preview - {grid_type}", cv2.resize(frame, (display_width, display_height)))
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    is_previewing = is_previewing_white = False
    cap.release()
    cv2.destroyAllWindows()


# ===================== GUI 启动 =====================

def create_gui():
    root = tk.Tk()
    root.title("原始画面检测系统 (无畸变校正)")
    root.geometry("600x300")

    ttk.Label(root, text="💡 当前模式：原始 1920x1080 画面直出", font=("微软雅黑", 12)).pack(pady=20)

    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=10)

    ttk.Button(btn_frame, text="开始检测 (粉色)",
               command=lambda: threading.Thread(target=detect_contours_by_ratio, args=((31.0, 32.0),),
                                                daemon=True).start()).grid(row=0, column=0, padx=10)
    ttk.Button(btn_frame, text="预览粉色",
               command=lambda: threading.Thread(target=preview_saved_contours, args=("hearing_aid",),
                                                daemon=True).start()).grid(row=0, column=1, padx=10)
    ttk.Button(btn_frame, text="预览白色",
               command=lambda: threading.Thread(target=preview_saved_contours, args=("white",),
                                                daemon=True).start()).grid(row=0, column=2, padx=10)

    root.mainloop()


if __name__ == "__main__":
    create_gui()