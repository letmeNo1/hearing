import cv2
import numpy as np
import json
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

# 全局变量
cap = None
is_running = False
# 改为百分比记录（0.0 到 20.0 之间的浮点数）
left_shrink_percent = 0.0
right_shrink_percent = 0.0
has_adjusted = False
cam_width = 1920
cam_height = 1080
params_path = "distortion_params.json"

save_flag = False
save_success = False

# 网格线参数
GRID_MAIN_INTERVAL = 100
GRID_SUB_INTERVAL = 20
GRID_MAIN_COLOR = (128, 128, 128)
GRID_SUB_COLOR = (64, 64, 64)
GRID_MAIN_THICK = 2
GRID_SUB_THICK = 1

left_val_label = None
right_val_label = None


def draw_grid(frame):
    h, w = frame.shape[:2]
    for x in range(0, w, GRID_SUB_INTERVAL):
        cv2.line(frame, (x, 0), (x, h), GRID_SUB_COLOR, GRID_SUB_THICK)
    for y in range(0, h, GRID_SUB_INTERVAL):
        cv2.line(frame, (0, y), (w, y), GRID_SUB_COLOR, GRID_SUB_THICK)
    for x in range(0, w, GRID_MAIN_INTERVAL):
        cv2.line(frame, (x, 0), (x, h), GRID_MAIN_COLOR, GRID_MAIN_THICK)
    for y in range(0, h, GRID_MAIN_INTERVAL):
        cv2.line(frame, (0, y), (w, y), GRID_MAIN_COLOR, GRID_MAIN_THICK)
    cv2.line(frame, (w // 2, 0), (w // 2, h), (0, 255, 0), 2)
    cv2.line(frame, (0, h // 2), (w, h // 2), (0, 255, 0), 2)
    return frame


def update_left_shrink(v):
    global left_shrink_percent, has_adjusted
    left_shrink_percent = float(v)
    has_adjusted = True
    if left_val_label:
        left_val_label.config(text=f"左侧剪裁比例：{left_shrink_percent:.1f}%")


def update_right_shrink(v):
    global right_shrink_percent, has_adjusted
    right_shrink_percent = float(v)
    has_adjusted = True
    if right_val_label:
        right_val_label.config(text=f"右侧剪裁比例：{right_shrink_percent:.1f}%")


def save_current_params():
    global save_flag, save_success
    try:
        # 将百分比转换为像素
        left_pixel = (left_shrink_percent / 100.0) * cam_width
        right_pixel = (right_shrink_percent / 100.0) * cam_width

        src_points = np.float32([
            [0, 0],
            [cam_width, 0],
            [cam_width + right_pixel, cam_height],
            [0 - left_pixel, cam_height]
        ])
        target_width = int(cam_width - left_pixel - right_pixel)
        target_height = cam_height

        dst_points = np.float32([
            [0, 0],
            [target_width, 0],
            [target_width, target_height],
            [0, target_height]
        ])
        M = cv2.getPerspectiveTransform(src_points, dst_points)

        params = {
            "perspective_matrix": M.tolist(),
            "left_shrink_percent": left_shrink_percent,
            "right_shrink_percent": right_shrink_percent,
            "left_pixel_offset": left_pixel,
            "right_pixel_offset": right_pixel,
            "original_size": [cam_width, cam_height],
            "cropped_size": [target_width, target_height]
        }
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=4)

        save_success = True
        save_flag = True
        messagebox.showinfo("保存成功",
                            f"校正参数已保存！\n左：{left_shrink_percent}%\n右：{right_shrink_percent}%\n目标宽度：{target_width}")
    except Exception as e:
        save_success = False
        save_flag = True
        messagebox.showerror("保存失败", f"保存出错：{str(e)}")


def quit_app():
    global is_running
    is_running = False
    time.sleep(0.1)
    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    root.quit()


def calibrate():
    global cap, is_running, save_flag, save_success
    cap = cv2.VideoCapture(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_height)
    is_running = True

    cv2.namedWindow("畸变校正预览 | 百分比标定", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("畸变校正预览 | 百分比标定", 1000, 600)

    while is_running:
        ret, frame = cap.read()
        if not ret:
            continue

        if not has_adjusted:
            display_frame = cv2.resize(frame, (1000, 600))
            display_frame = draw_grid(display_frame)
            cv2.putText(display_frame, "Original Mode (Grid On)", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        else:
            # 实时计算百分比对应的像素
            l_pix = (left_shrink_percent / 100.0) * cam_width
            r_pix = (right_shrink_percent / 100.0) * cam_width

            target_width = int(cam_width - l_pix - r_pix)
            target_width = max(target_width, 100)

            src_points = np.float32([
                [0, 0], [cam_width, 0],
                [cam_width + r_pix, cam_height],
                [0 - l_pix, cam_height]
            ])
            dst_points = np.float32([
                [0, 0], [target_width, 0],
                [target_width, cam_height],
                [0, cam_height]
            ])

            M = cv2.getPerspectiveTransform(src_points, dst_points)
            corrected_frame = cv2.warpPerspective(frame, M, (target_width, cam_height))

            display_frame = cv2.resize(corrected_frame, (1000, 600))
            display_frame = draw_grid(display_frame)

            cv2.putText(display_frame, f"L: {left_shrink_percent}% | R: {right_shrink_percent}%",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            cv2.putText(display_frame, f"Target Width: {target_width}px",
                        (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        if save_flag:
            msg = "Saved Successfully!" if save_success else "Save Failed!"
            cv2.putText(display_frame, msg, (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            save_flag = False

        cv2.imshow("畸变校正预览 | 百分比标定", display_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            is_running = False
        elif key == ord('s'):
            save_current_params()

    cap.release()
    cv2.destroyAllWindows()


def create_gui():
    global root, left_val_label, right_val_label
    root = tk.Tk()
    root.title("畸变校正 | 百分比模式")
    root.geometry("500x420")
    root.configure(bg="#f0f0f0")

    # ---------------------- 滑块区域 ----------------------
    tk.Label(root, text="左侧向内收缩百分比 (0-20%)：", font=("微软雅黑", 10), bg="#f0f0f0").pack(pady=6)
    # resolution=0.1 表示支持 0.1% 的微调
    left_slider = tk.Scale(root, from_=0, to=20, command=update_left_shrink,
                           orient=tk.HORIZONTAL, length=450, resolution=0.1)
    left_slider.set(left_shrink_percent)
    left_slider.pack(padx=20)
    left_val_label = ttk.Label(root, text=f"左侧剪裁比例：{left_shrink_percent}%", font=("微软雅黑", 9))
    left_val_label.pack()

    tk.Label(root, text="右侧向内收缩百分比 (0-20%)：", font=("微软雅黑", 10), bg="#f0f0f0").pack(pady=6)
    right_slider = tk.Scale(root, from_=0, to=20, command=update_right_shrink,
                            orient=tk.HORIZONTAL, length=450, resolution=0.1)
    right_slider.set(right_shrink_percent)
    right_slider.pack(padx=20)
    right_val_label = ttk.Label(root, text=f"右侧剪裁比例：{right_shrink_percent}%", font=("微软雅黑", 9))
    right_val_label.pack()

    # ---------------------- 按钮区域 ----------------------
    btn_frame = tk.Frame(root, bg="#f0f0f0")
    btn_frame.pack(pady=20)

    tk.Button(btn_frame, text=" 保存校正参数 ", font=("微软雅黑", 10, "bold"), bg="#4CAF50", fg="white",
              padx=20, pady=5, command=save_current_params).grid(row=0, column=0, padx=10)

    tk.Button(btn_frame, text=" 退出程序 ", font=("微软雅黑", 10, "bold"), bg="#f44336", fg="white",
              padx=20, pady=5, command=quit_app).grid(row=0, column=1, padx=10)

    ttk.Label(root,
              text="📌 逻辑说明：\n1. 滑块数值为画面宽度的百分比 (%)\n2. 最终会根据 1920 像素自动换算并保存矩阵\n3. 适合不同分辨率下的通用校正记录",
              font=("微软雅黑", 9), foreground="#555").pack(pady=5)

    preview_thread = threading.Thread(target=calibrate, daemon=True)
    preview_thread.start()
    root.mainloop()


if __name__ == "__main__":
    create_gui()