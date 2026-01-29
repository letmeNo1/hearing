import cv2
import numpy as np
import json
import os
from tkinter import messagebox

# 常量定义
PARAMS_FILE = "calibration_params.json"
CHARGING_CASE_BORDER_DATA = "charging_case_border.json"


def adjust_charging_case_border():
    # 1. 加载透视变换参数
    M = None
    size = (1920, 1080)
    if os.path.exists(PARAMS_FILE):
        with open(PARAMS_FILE, 'r') as f:
            d = json.load(f)
            M = np.array(d['perspective_matrix'])
            size = tuple(d['cropped_size'])

    # 2. 读取当前坐标或设为默认值
    if os.path.exists(CHARGING_CASE_BORDER_DATA):
        with open(CHARGING_CASE_BORDER_DATA, "r") as f:
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
    drag_threshold = 80  # 增大阈值，从40改为80，更容易点中

    def mouse_callback(event, x, y, flags, param):
        nonlocal x1, y1, x2, y2, dragging_tl, dragging_br

        # 坐标转换：预览是 960x540 (0.5倍)，实际计算用 1920x1080
        real_x, real_y = x * 2, y * 2

        if event == cv2.EVENT_LBUTTONDOWN:
            # 判断点击左上角（增大阈值，更容易触发）
            if abs(real_x - x1) < drag_threshold and abs(real_y - y1) < drag_threshold:
                dragging_tl = True
                print(f"触发左上角拖动: TL({x1},{y1}) 点击位置({real_x},{real_y})")
            # 判断点击右下角（核心修复：增大阈值）
            elif abs(real_x - x2) < drag_threshold and abs(real_y - y2) < drag_threshold:
                dragging_br = True
                print(f"触发右下角拖动: BR({x2},{y2}) 点击位置({real_x},{real_y})")

        elif event == cv2.EVENT_MOUSEMOVE:
            # 拖动左上角
            if dragging_tl:
                x1, y1 = real_x, real_y
            # 拖动右下角（确保逻辑和左上一致）
            elif dragging_br:
                x2, y2 = real_x, real_y

        elif event == cv2.EVENT_LBUTTONUP:
            # 释放拖动状态
            dragging_tl = dragging_br = False
            print("停止拖动")

    # 3. 启动摄像头
    cap = cv2.VideoCapture(1)
    if not cap.isOpened(): 
        cap = cv2.VideoCapture(0)
        print("警告：未检测到摄像头1，切换到摄像头0")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    win_name = "Manual Adjust: Drag Green/Red dots. (S: Save, Q: Quit)"
    cv2.namedWindow(win_name)
    cv2.setMouseCallback(win_name, mouse_callback)

    while True:
        ret, raw = cap.read()
        if not ret: 
            print("摄像头读取失败，退出")
            break

        # 应用校正变换
        frame = cv2.warpPerspective(raw, M, size) if M is not None else raw

        # 绘制交互元素
        # 绘制主矩形
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 255), 2)
        # 绘制左上角把手 (绿色) - 增大圆点尺寸，更容易识别
        cv2.circle(frame, (int(x1), int(y1)), 15, (0, 255, 0), -1)
        # 绘制右下角把手 (红色) - 增大圆点尺寸，核心修复
        cv2.circle(frame, (int(x2), int(y2)), 15, (0, 0, 255), -1)

        # 实时显示坐标信息（增加右下角坐标提示）
        info = f"TL:({int(x1)},{int(y1)}) BR:({int(x2)},{int(y2)}) 阈值:{drag_threshold}"
        cv2.putText(frame, info, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

        # 窗口缩放显示（保持0.5倍缩放）
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
            with open(CHARGING_CASE_BORDER_DATA, "w") as f:
                json.dump(save_data, f, indent=4)
            messagebox.showinfo("成功", f"充电盒边框坐标已更新！\n起始点: {int(min_x)}, {int(min_y)} 尺寸: {int(w)}x{int(h)}")
            break
        elif key == ord('q') or cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
            print("用户退出调整")
            break

    cap.release()
    cv2.destroyAllWindows()

# 测试调用（可选）
if __name__ == "__main__":
    adjust_charging_case_border()