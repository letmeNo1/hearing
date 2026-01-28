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
# 精准收缩参数：左下向左、右下向右（数值=剪裁像素数）
left_left_shrink = 0  # 左下向左收缩/剪裁像素数
right_right_shrink = 0  # 右下向右收缩/剪裁像素数
has_adjusted = False  # 未拖动=纯原图
cam_width = 1920
cam_height = 1080
params_path = "distortion_params.json"
# 线程通信：用于保存时传递提示
save_flag = False
save_success = False
# 网格线参数（可自定义）
GRID_MAIN_INTERVAL = 100  # 主网格间隔（像素）
GRID_SUB_INTERVAL = 20  # 次网格间隔（像素）
GRID_MAIN_COLOR = (128, 128, 128)  # 主网格颜色（灰色）
GRID_SUB_COLOR = (64, 64, 64)  # 次网格颜色（深灰色）
GRID_MAIN_THICK = 2  # 主网格线宽
GRID_SUB_THICK = 1  # 次网格线宽

# 实时数值标签
left_val_label = None
right_val_label = None


def draw_grid(frame):
    """在画面上绘制辅助标定网格线"""
    h, w = frame.shape[:2]

    # 绘制次网格线（细线，密集）
    for x in range(0, w, GRID_SUB_INTERVAL):
        cv2.line(frame, (x, 0), (x, h), GRID_SUB_COLOR, GRID_SUB_THICK)
    for y in range(0, h, GRID_SUB_INTERVAL):
        cv2.line(frame, (0, y), (w, y), GRID_SUB_COLOR, GRID_SUB_THICK)

    # 绘制主网格线（粗线，稀疏，更醒目）
    for x in range(0, w, GRID_MAIN_INTERVAL):
        cv2.line(frame, (x, 0), (x, h), GRID_MAIN_COLOR, GRID_MAIN_THICK)
    for y in range(0, h, GRID_MAIN_INTERVAL):
        cv2.line(frame, (0, y), (w, y), GRID_MAIN_COLOR, GRID_MAIN_THICK)

    # 绘制中心十字线（最醒目）
    cv2.line(frame, (w // 2, 0), (w // 2, h), (0, 255, 0), 2)
    cv2.line(frame, (0, h // 2), (w, h // 2), (0, 255, 0), 2)

    return frame


def update_left_shrink(v):
    """左滑块：左下向左收缩/剪裁（数值=剪裁像素数）"""
    global left_left_shrink, has_adjusted
    left_left_shrink = int(float(v))
    has_adjusted = True
    if left_val_label:
        left_val_label.config(text=f"左下向左剪裁：{left_left_shrink} 像素")


def update_right_shrink(v):
    """右滑块：右下向右收缩/剪裁（数值=剪裁像素数）"""
    global right_right_shrink, has_adjusted
    right_right_shrink = int(float(v))
    has_adjusted = True
    if right_val_label:
        right_val_label.config(text=f"右下向右剪裁：{right_right_shrink} 像素")


def save_current_params():
    """保存当前校正参数（按钮调用）"""
    global save_flag, save_success
    try:
        # 计算透视矩阵（包含剪裁逻辑）
        src_points = np.float32([
            [0, 0],
            [cam_width, 0],
            [cam_width + right_right_shrink, cam_height],
            [0 - left_left_shrink, cam_height]
        ])
        # 目标尺寸：原始尺寸 - 左右剪裁像素数
        target_width = cam_width - left_left_shrink - right_right_shrink
        target_height = cam_height
        dst_points = np.float32([
            [0, 0],
            [target_width, 0],
            [target_width, target_height],
            [0, target_height]
        ])
        M = cv2.getPerspectiveTransform(src_points, dst_points)

        # 保存参数到JSON（包含剪裁尺寸）
        params = {
            "perspective_matrix": M.tolist(),
            "left_left_shrink": left_left_shrink,
            "right_right_shrink": right_right_shrink,
            "original_size": [cam_width, cam_height],
            "cropped_size": [target_width, target_height]
        }
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(params, f, indent=4)

        save_success = True
        save_flag = True
        messagebox.showinfo("保存成功",
                            f"校正参数已保存！\n左剪裁：{left_left_shrink}像素\n右剪裁：{right_right_shrink}像素\n剪裁后尺寸：{target_width}x{target_height}")
        print(
            f"✅ 参数已保存：左剪裁={left_left_shrink}，右剪裁={right_right_shrink}，剪裁后尺寸={target_width}x{target_height}")
    except Exception as e:
        save_success = False
        save_flag = True
        messagebox.showerror("保存失败", f"保存出错：{str(e)}")
        print(f"❌ 保存失败：{str(e)}")


def quit_app():
    """退出程序（按钮调用）"""
    global is_running
    is_running = False
    time.sleep(0.1)  # 等待预览线程退出
    # 释放资源
    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    root.quit()  # 关闭GUI


def calibrate():
    """预览线程：打开=原图+网格线，拖动校正+精准剪裁"""
    global cap, is_running, save_flag, save_success
    cap = cv2.VideoCapture(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cam_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cam_height)
    is_running = True

    # 预览窗口
    cv2.namedWindow("畸变校正预览 | 网格线辅助标定（精准剪裁）", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("畸变校正预览 | 网格线辅助标定（精准剪裁）", 1000, 600)

    while is_running:
        ret, frame = cap.read()
        if not ret:
            continue

        # 核心：纯原图/实时校正+剪裁逻辑
        if not has_adjusted:
            display_frame = cv2.resize(frame, (1000, 600))
            # 添加网格线（原图也显示网格，方便初始标定）
            display_frame = draw_grid(display_frame)
            cv2.putText(display_frame, "当前：纯原图 + 辅助网格线",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
        else:
            # 1. 计算剪裁后的目标尺寸（收缩多少，剪裁多少）
            target_width = cam_width - left_left_shrink - right_right_shrink
            target_height = cam_height
            # 防止剪裁过度（宽度不能小于100）
            target_width = max(target_width, 100)

            # 2. 透视变换（校正畸变）
            src_points = np.float32([
                [0, 0],
                [cam_width, 0],
                [cam_width + right_right_shrink, cam_height],
                [0 - left_left_shrink, cam_height]
            ])
            dst_points = np.float32([
                [0, 0],
                [target_width, 0],
                [target_width, target_height],
                [0, target_height]
            ])
            M = cv2.getPerspectiveTransform(src_points, dst_points)
            corrected_frame = cv2.warpPerspective(frame, M, (target_width, target_height))

            # 3. 预览缩放（适配1000x600窗口）
            display_frame = cv2.resize(corrected_frame, (1000, 600))

            # 添加网格线（校正+剪裁后显示，方便精准对齐）
            display_frame = draw_grid(display_frame)

            # 方向箭头+数值标注（明确显示剪裁像素数）
            cv2.arrowedLine(display_frame, (100, 550), (100 - left_left_shrink // 2, 550),
                            (0, 0, 255), 3, tipLength=0.2)
            cv2.arrowedLine(display_frame, (900, 550), (900 + right_right_shrink // 2, 550),
                            (255, 0, 0), 3, tipLength=0.2)
            cv2.putText(display_frame, f"左剪裁：{left_left_shrink}像素 | 右剪裁：{right_right_shrink}像素",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            # 显示剪裁后尺寸
            cv2.putText(display_frame, f"剪裁后尺寸：{target_width}x{target_height}",
                        (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # 保存提示（响应按钮保存）
        if save_flag:
            if save_success:
                cv2.putText(display_frame, "✅ 参数已保存！", (20, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            else:
                cv2.putText(display_frame, "❌ 保存失败！", (20, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            save_flag = False  # 重置保存标记

        # 通用操作提示（标注按钮+快捷键）
        cv2.putText(display_frame, "操作：GUI按钮保存/退出 | 快捷键S=保存 Q=退出",
                    (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.imshow("畸变校正预览 | 网格线辅助标定（精准剪裁）", display_frame)

        # 键盘快捷键（备用）
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            is_running = False
        elif key == ord('s'):
            save_current_params()

    # 释放资源
    cap.release()
    cv2.destroyAllWindows()


def create_gui():
    """GUI界面：滑块+保存/退出按钮"""
    global root, left_val_label, right_val_label
    root = tk.Tk()
    root.title("畸变校正 | 精准剪裁（收缩=剪裁像素）")
    root.geometry("500x400")
    root.configure(bg="#f0f0f0")
    root.resizable(False, False)  # 固定窗口大小

    # ---------------------- 滑块区域 ----------------------
    # 左滑块：左下向左剪裁（数值=剪裁像素数）
    tk.Label(root, text="左下向左剪裁（0-400，步长5）：",
             font=("微软雅黑", 10), bg="#f0f0f0").pack(pady=6)
    left_slider = tk.Scale(root, from_=0, to=400, command=update_left_shrink,
                           orient=tk.HORIZONTAL, length=450, resolution=5)
    left_slider.set(left_left_shrink)
    left_slider.pack(fill=tk.X, padx=20)
    left_val_label = ttk.Label(root, text=f"左下向左剪裁：{left_left_shrink} 像素", font=("微软雅黑", 9))
    left_val_label.pack(pady=2)

    # 右滑块：右下向右剪裁（数值=剪裁像素数）
    tk.Label(root, text="右下向右剪裁（0-400，步长5）：",
             font=("微软雅黑", 10), bg="#f0f0f0").pack(pady=6)
    right_slider = tk.Scale(root, from_=0, to=400, command=update_right_shrink,
                            orient=tk.HORIZONTAL, length=450, resolution=5)
    right_slider.set(right_right_shrink)
    right_slider.pack(fill=tk.X, padx=20)
    right_val_label = ttk.Label(root, text=f"右下向右剪裁：{right_right_shrink} 像素", font=("微软雅黑", 9))
    right_val_label.pack(pady=2)

    # ---------------------- 按钮区域 ----------------------
    btn_frame = tk.Frame(root, bg="#f0f0f0")
    btn_frame.pack(pady=15)

    # 保存按钮（绿色，醒目）
    save_btn = tk.Button(btn_frame, text=" 保存校正参数 ",
                         font=("微软雅黑", 10, "bold"), bg="#4CAF50", fg="white",
                         padx=20, pady=5, command=save_current_params)
    save_btn.grid(row=0, column=0, padx=10)

    # 退出按钮（红色，醒目）
    quit_btn = tk.Button(btn_frame, text=" 退出程序 ",
                         font=("微软雅黑", 10, "bold"), bg="#f44336", fg="white",
                         padx=20, pady=5, command=quit_app)
    quit_btn.grid(row=0, column=1, padx=10)

    # ---------------------- 提示区域 ----------------------
    ttk.Label(root, text="📌 核心逻辑：\n"
                         "1. 滑块数值 = 画面剪裁像素数\n"
                         "2. 左滑块右拖 → 剪裁左侧N像素（左下向左收）\n"
                         "3. 右滑块右拖 → 剪裁右侧N像素（右下向右收）\n"
                         "4. 调整至画面成矩形后点击【保存】",
              font=("微软雅黑", 9), foreground="#555").pack(pady=5)

    # 启动预览线程
    preview_thread = threading.Thread(target=calibrate, daemon=True)
    preview_thread.start()

    root.mainloop()


if __name__ == "__main__":
    create_gui()