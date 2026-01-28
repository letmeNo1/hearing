import cv2
import numpy as np
import json
import os
from tkinter import messagebox

# 常量定义
PARAMS_FILE = "calibration_params.json"
WHITE_DATA = "black_border.json"


def adjust_black_border():
    # 1. 加载透视变换参数
    M = None
    size = (1920, 1080)
    if os.path.exists(PARAMS_FILE):
        with open(PARAMS_FILE, 'r') as f:
            d = json.load(f)
            M = np.array(d['perspective_matrix'])
            size = tuple(d['cropped_size'])

    # 2. 读取当前坐标或设为默认值
    if os.path.exists(WHITE_DATA):
        with open(WHITE_DATA, "r") as f:
            data = json.load(f)
            r = data["contours"][0]["bounding_rect"]
            x1, y1 = r[0], r[1]
            x2, y2 = r[0] + r[2], r[1] + r[3]
    else:
        # 默认值：取画面中央区域
        x1, y1, x2, y2 = 400, 200, 1500, 800

    # 鼠标交互逻辑
    dragging_tl = False  # 拖动左上角
    dragging_br = False  # 拖动右下角

    def mouse_callback(event, x, y, flags, param):
        nonlocal x1, y1, x2, y2, dragging_tl, dragging_br

        # 坐标转换：预览是 960x540 (0.5倍)，实际计算用 1920x1080
        real_x, real_y = x * 2, y * 2

        if event == cv2.EVENT_LBUTTONDOWN:
            # 判断点击位置是否靠近左上角点 (10 像素阈值)
            if abs(real_x - x1) < 40 and abs(real_y - y1) < 40:
                dragging_tl = True
            # 判断点击位置是否靠近右下角点
            elif abs(real_x - x2) < 40 and abs(real_y - y2) < 40:
                dragging_br = True

        elif event == cv2.EVENT_MOUSEMOVE:
            if dragging_tl:
                x1, y1 = real_x, real_y
            elif dragging_br:
                x2, y2 = real_x, real_y

        elif event == cv2.EVENT_LBUTTONUP:
            dragging_tl = dragging_br = False

    # 3. 启动摄像头
    cap = cv2.VideoCapture(1)
    if not cap.isOpened(): cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    win_name = "Manual Adjust: Drag Green/Red dots. (S: Save, Q: Quit)"
    cv2.namedWindow(win_name)
    cv2.setMouseCallback(win_name, mouse_callback)

    while True:
        ret, raw = cap.read()
        if not ret: break

        # 应用校正变换
        frame = cv2.warpPerspective(raw, M, size) if M is not None else raw

        # 绘制交互元素
        # 绘制主矩形
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 255), 2)
        # 绘制左上角把手 (绿色)
        cv2.circle(frame, (int(x1), int(y1)), 12, (0, 255, 0), -1)
        # 绘制右下角把手 (红色)
        cv2.circle(frame, (int(x2), int(y2)), 12, (0, 0, 255), -1)

        # 实时显示坐标信息
        info = f"TL:({int(x1)},{int(y1)}) BR:({int(x2)},{int(y2)})"
        cv2.putText(frame, info, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

        # 窗口缩放显示
        cv2.imshow(win_name, cv2.resize(frame, (960, 540)))

        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):  # 保存
            # 格式化数据：确保 x1, y1 始终是起点
            min_x, min_y = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)

            save_data = {
                "contours": [{
                    "bounding_rect": [int(min_x), int(min_y), int(w), int(h)]
                }]
            }
            with open(WHITE_DATA, "w") as f:
                json.dump(save_data, f, indent=4)
            messagebox.showinfo("成功", f"黑边坐标已更新！\n起始点: {int(min_x)}, {int(min_y)}")
            break
        elif key == ord('q') or cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
            break

    cap.release()
    cv2.destroyAllWindows()