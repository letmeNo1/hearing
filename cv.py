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

# ===================== 两套独立网格配置，完全分开 =====================
# 1. 粉色边框专属（还原你最初的逻辑：14等分计算，13列显示，4行，保留偏移）
PINK_GRID_ROWS = 4
PINK_GRID_COLS_CALC = 14  # 宽度按14等分
PINK_GRID_COLS_DISPLAY = 13  # 实际画13列
PINK_GRID_COLOR = (255, 0, 0)
PINK_GRID_THICKNESS = 2

# 2. 白色边框专属（你新要求：5列2行，无偏移，10等分）
WHITE_GRID_ROWS = 2
WHITE_GRID_COLS = 5  # 5列
WHITE_BORDER_COLOR = (255, 255, 255)  # 白色外框
WHITE_BORDER_THICKNESS = 5
WHITE_GRID_COLOR = (255, 0, 0)
WHITE_GRID_THICKNESS = 2

# 白色边框独立JSON
WHITE_BORDER_JSON_PATH = "black_border.json"

# ===================== 新增：畸变+剪裁参数（全局） =====================
DISTORTION_PARAMS_PATH = "distortion_params.json"
perspective_matrix = None
# 剪裁参数（响应标定的数值）
left_crop = 0  # 左下向左剪裁像素数
right_crop = 0  # 右下向右剪裁像素数
cropped_width = 1920  # 剪裁后的宽度
cropped_height = 1080  # 剪裁后的高度


def load_distortion_params():
    """加载预标定的畸变+剪裁参数（双倍剪裁，确保左右都有值）"""
    global perspective_matrix, left_crop, right_crop, cropped_width, cropped_height
    global cam_width, cam_height, cam_total_area, display_width, display_height

    if not os.path.exists(DISTORTION_PARAMS_PATH):
        messagebox.showwarning("提示", f"未找到畸变校正参数文件 {DISTORTION_PARAMS_PATH}\n将使用原始画面")
        perspective_matrix = None
        cropped_width = cam_width
        cropped_height = cam_height
        return False

    try:
        with open(DISTORTION_PARAMS_PATH, "r", encoding="utf-8") as f:
            params = json.load(f)

        # 加载透视矩阵
        perspective_matrix = np.array(params["perspective_matrix"], dtype=np.float32)
        # 1. 加载原始剪裁参数（确保左右都有值，避免其中一个为0）
        left_crop_original = params.get("left_left_shrink", 0)
        right_crop_original = params.get("right_right_shrink", 0)

        # 2. 双倍剪裁（强制确保左右都至少剪裁10px，避免其中一个为0）
        left_crop = max(left_crop_original * 2, 10)  # 左剪裁×2，最小10px
        right_crop = max(right_crop_original * 2, 10)  # 右剪裁×2，最小10px

        # 3. 重新计算剪裁后的尺寸（安全边界：左右剪裁总和<1920）
        original_width = 1920
        original_height = 1080
        # 确保剪裁后宽度>200px，且左剪裁<右边界
        max_total_crop = original_width - 200
        total_crop = left_crop + right_crop
        if total_crop > max_total_crop:
            # 按比例分配剪裁值，避免过度剪裁
            ratio = max_total_crop / total_crop
            left_crop = int(left_crop * ratio)
            right_crop = int(right_crop * ratio)

        cropped_width = original_width - left_crop - right_crop
        cropped_height = original_height

        # 更新全局尺寸
        cam_width = cropped_width
        cam_height = cropped_height
        cam_total_area = cam_width * cam_height
        display_width = int(cam_width * DISPLAY_SCALE)
        display_height = int(cam_height * DISPLAY_SCALE)

        # 调试信息：打印剪裁范围，方便核对
        print(f"✅ 成功加载畸变+双倍剪裁参数")
        print(f"   原始剪裁：左={left_crop_original}px | 右={right_crop_original}px")
        print(f"   双倍剪裁：左={left_crop}px | 右={right_crop}px")
        print(f"   剪裁范围：[{left_crop} : {original_width - right_crop}]")
        print(f"   最终尺寸：{cropped_width}x{cropped_height}")
        return True
    except Exception as e:
        messagebox.showerror("错误", f"加载畸变参数失败：{e}\n将使用原始画面")
        perspective_matrix = None
        cropped_width = cam_width
        cropped_height = cam_height
        return False


def correct_distortion(frame):
    """执行畸变校正+左右双向剪裁（确保两边都剪掉）"""
    if frame is None or perspective_matrix is None:
        return frame

    # 第一步：透视变换（校正畸变，输出原始尺寸）
    corrected = cv2.warpPerspective(
        frame,
        perspective_matrix,
        (1920, 1080)  # 固定输出1920x1080，确保剪裁索引有效
    )

    # 第二步：安全双向剪裁（加边界检查，避免索引错误）
    original_width = 1920
    # 左边界：最小0，最大original_width - right_crop - 10
    left_bound = max(left_crop, 0)
    # 右边界：最大original_width，最小left_bound + 200
    right_bound = min(original_width - right_crop, original_width)
    # 确保右边界>左边界，避免切片为空
    if right_bound <= left_bound:
        right_bound = left_bound + 200
        print(f"⚠️ 剪裁范围异常，自动调整右边界：{left_bound} → {right_bound}")

    # 核心：双向剪裁（左剪left_bound，右剪original_width - right_bound）
    cropped = corrected[:, left_bound: right_bound]

    # 第三步：调整到目标尺寸（确保比例正确）
    cropped = cv2.resize(cropped, (cropped_width, cropped_height), interpolation=cv2.INTER_AREA)

    # 调试：打印实际剪裁后的尺寸
    print(f"📏 实际剪裁后尺寸：{cropped.shape[1]}x{cropped.shape[0]}")

    return cropped

def correct_distortion(frame):
    """执行畸变校正+双倍剪裁（彻底去掉畸变区域）"""
    if frame is None or perspective_matrix is None:
        return frame

    # 第一步：透视变换（校正畸变）
    corrected = cv2.warpPerspective(
        frame,
        perspective_matrix,
        (1920, 1080)  # 先输出原始尺寸的校正画面
    )

    # 第二步：硬剪裁（使用双倍后的剪裁像素）
    # 左剪裁left_crop像素，右剪裁right_crop像素
    cropped = corrected[:, left_crop: 1920 - right_crop]

    # 确保剪裁后的尺寸与双倍剪裁后的目标一致
    if cropped.shape[1] != cropped_width or cropped.shape[0] != cropped_height:
        cropped = cv2.resize(cropped, (cropped_width, cropped_height))

    return cropped


def correct_distortion(frame):
    """执行畸变校正+精准剪裁（完全响应标定的剪裁数值）"""
    if frame is None or perspective_matrix is None:
        return frame

    # 第一步：透视变换（校正畸变）+ 直接输出剪裁后的尺寸
    corrected = cv2.warpPerspective(
        frame,
        perspective_matrix,
        (cropped_width, cropped_height)  # 核心：输出剪裁后的真实尺寸
    )
    return corrected


def init_camera():
    """初始化摄像头 + 加载畸变+剪裁参数"""
    global cap
    # 先加载畸变+剪裁参数（更新全局尺寸）
    load_distortion_params()

    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        messagebox.showerror("错误", "❌ 无法打开摄像头！")
        return False

    # 摄像头仍设为原始尺寸（畸变校正需要原始帧）
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    return True


# ===================== 粉色边框专用网格绘制（适配剪裁后尺寸） =====================
def draw_pink_grid(frame, target_rect):
    """
    完全还原你最初的粉色框网格，适配剪裁后的尺寸：
    14等分宽度，显示13列，4行
    x偏移：x_rect + 半个格子宽度
    """
    if target_rect is None:
        return frame
    frame_copy = frame.copy()
    x_rect, y_rect, w_rect, h_rect = target_rect

    # 14等分计算单个格子宽度（基于剪裁后的画面尺寸）
    grid_w = w_rect / PINK_GRID_COLS_CALC
    grid_h = h_rect / PINK_GRID_ROWS

    # 你要求的偏移：x_rect + 半个格子宽度
    x_rect_new = int(x_rect + grid_w / 2)
    y_rect_new = int(y_rect)
    h_rect_new = int(h_rect)

    # 竖线：12条，对应13列
    for col in range(1, PINK_GRID_COLS_DISPLAY):
        x = int(x_rect_new + col * grid_w)
        cv2.line(frame_copy, (x, y_rect_new), (x, y_rect_new + h_rect_new),
                 PINK_GRID_COLOR, PINK_GRID_THICKNESS)
        cv2.putText(frame_copy, str(col), (x - 10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, PINK_GRID_COLOR, 2)

    # 横线：3条，对应4行
    for row in range(1, PINK_GRID_ROWS):
        y = int(y_rect_new + row * grid_h)
        line_end_x = int(x_rect_new + PINK_GRID_COLS_DISPLAY * grid_w)
        cv2.line(frame_copy, (x_rect_new, y), (line_end_x, y),
                 PINK_GRID_COLOR, PINK_GRID_THICKNESS)
        cv2.putText(frame_copy, f"Row {row}", (10, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, PINK_GRID_COLOR, 2)

    # 网格小框：4行13列
    for row in range(PINK_GRID_ROWS):
        for col in range(PINK_GRID_COLS_DISPLAY):
            x1 = int(x_rect_new + col * grid_w)
            y1 = int(y_rect_new + row * grid_h)
            x2 = int(x_rect_new + (col + 1) * grid_w)
            y2 = int(y_rect_new + (row + 1) * grid_h)
            cv2.rectangle(frame_copy, (x1, y1), (x2, y2), PINK_GRID_COLOR, 1)
            cv2.putText(frame_copy, f"{row}-{col}", (x1 + 5, y1 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, PINK_GRID_COLOR, 1)

    return frame_copy


# ===================== 白色边框专用网格绘制（适配剪裁后尺寸） =====================
def draw_white_grid(frame, target_rect):
    """
    白色框内部网格，适配剪裁后的尺寸：
    5列2行，无任何偏移，直接从原始x_rect,y_rect开始画
    """
    if target_rect is None:
        return frame
    frame_copy = frame.copy()
    x_rect, y_rect, w_rect, h_rect = target_rect

    # 5列等分（基于剪裁后的画面尺寸）
    grid_w = w_rect / WHITE_GRID_COLS
    grid_h = h_rect / WHITE_GRID_ROWS

    # 白色边框：彻底无偏移
    x_draw = int(x_rect)
    y_draw = int(y_rect)

    # 竖线：4条 → 5列
    for col in range(1, WHITE_GRID_COLS):
        x = int(x_draw + col * grid_w)
        cv2.line(frame_copy, (x, y_draw), (x, y_draw + h_rect),
                 WHITE_GRID_COLOR, WHITE_GRID_THICKNESS)

    # 横线：1条 → 2行
    for row in range(1, WHITE_GRID_ROWS):
        y = int(y_draw + row * grid_h)
        line_end = int(x_draw + WHITE_GRID_COLS * grid_w)
        cv2.line(frame_copy, (x_draw, y), (line_end, y),
                 WHITE_GRID_COLOR, WHITE_GRID_THICKNESS)

    # 画10个小格子
    for row in range(WHITE_GRID_ROWS):
        for col in range(WHITE_GRID_COLS):
            x1 = int(x_draw + col * grid_w)
            y1 = int(y_draw + row * grid_h)
            x2 = int(x_draw + (col + 1) * grid_w)
            y2 = int(y_draw + (row + 1) * grid_h)
            cv2.rectangle(frame_copy, (x1, y1), (x2, y2), WHITE_GRID_COLOR, 1)
            cv2.putText(frame_copy, f"{row}-{col}", (x1 + 5, y1 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, WHITE_GRID_COLOR, 1)

    return frame_copy


def detect_contours_by_ratio(target_ratio_range, color=(192, 203, 255)):
    """粉色边框检测，使用剪裁后的尺寸+14等分13列4行网格"""
    global cap, is_detecting

    if not init_camera():
        return

    is_detecting = True
    min_ratio, max_ratio = target_ratio_range
    detected_contours = []

    adaptive_block_size = 11
    adaptive_c = 2
    canny_low = 60
    canny_high = 180

    print("\n🔍 开始检测【外接矩形31-32%】粉色外轮廓")
    print(f"📐 粉色网格：{PINK_GRID_ROWS}行×{PINK_GRID_COLS_DISPLAY}列（14等分），保留偏移")
    print(f"📏 基于剪裁后尺寸：{cropped_width}x{cropped_height}（左裁{left_crop}，右裁{right_crop}）")
    print("👉 按 q 退出检测窗口")

    frame_count = 0
    while is_detecting:
        ret, frame = cap.read()
        if not ret:
            print("❌ 读取摄像头失败，重试中...")
            continue

        # 核心：先做畸变校正+剪裁（得到真实剪裁后的画面）
        frame = correct_distortion(frame)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 0)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
            adaptive_block_size if adaptive_block_size % 2 == 1 else adaptive_block_size + 1,
            adaptive_c
        )
        kernel_close = np.ones((5, 5), np.uint8)
        kernel_open = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open, iterations=1)
        edges = cv2.Canny(binary, canny_low, canny_high)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        frame_copy = frame.copy()
        current_detected = []
        target_rect = None

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 2000:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            rect_area = w * h
            # 关键：基于剪裁后的总面积计算比例（响应剪裁）
            rect_ratio = (rect_area / cam_total_area) * 100

            if 31.0 <= rect_ratio <= 32.0:
                min_rect = cv2.minAreaRect(cnt)
                box = cv2.boxPoints(min_rect)
                box = np.int32(box)
                current_detected.append({
                    "contour_area": round(area, 2),
                    "area_ratio": round((area / cam_total_area) * 100, 2),
                    "rect_area": round(rect_area, 2),
                    "rect_ratio": round(rect_ratio, 2),
                    "contour_coordinates": cnt.reshape(-1, 2).tolist(),
                    "bounding_box_coordinates": box.tolist(),
                    "bounding_rect": (x, y, w, h),
                    "cropped_size": [cropped_width, cropped_height]  # 记录剪裁尺寸
                })
                cv2.drawContours(frame_copy, [box], 0, color, 4)
                cv2.putText(frame_copy, f"Rect Ratio:{rect_ratio:.1f}%",
                            (x + 10, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
                target_rect = (x, y, w, h)

        # 调用粉色专属网格（适配剪裁后尺寸）
        frame_final = draw_pink_grid(frame_copy, target_rect)
        # 缩放显示（基于剪裁后的尺寸）
        frame_display = cv2.resize(frame_final, (display_width, display_height))
        cv2.imshow(f"Detection - Pink 13cols (Cropped {cropped_width}x{cropped_height})", frame_display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("🛑 用户手动终止检测")
            break
        if current_detected:
            detected_contours = current_detected
            break

        frame_count += 1
        if frame_count % 10 == 0:
            print(f"⏳ 已检测 {frame_count} 帧，未找到目标...")

    if detected_contours:
        save_contour_to_json(detected_contours, color)
        messagebox.showinfo("成功",
                            f"✅ 检测到 {len(detected_contours)} 个目标\n"
                            f"粉色网格：4行13列（14等分）\n"
                            f"剪裁后尺寸：{cropped_width}x{cropped_height}")
    else:
        if is_detecting:
            messagebox.showwarning("警告", "⚠️ 未检测到符合条件的粉色外轮廓")

    is_detecting = False
    cap.release()
    cv2.destroyAllWindows()
    return detected_contours


def save_contour_to_json(contours_data, color):
    """粉色结果保存到 contour_result.json（包含剪裁信息）"""
    result = {
        "camera_info": {
            "original_size": [1920, 1080],
            "cropped_size": [cropped_width, cropped_height],
            "crop_params": {"left": left_crop, "right": right_crop}
        },
        "grid_type": "pink_14calc_13display",
        "contours": contours_data
    }
    with open("contour_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


def load_contour_from_json():
    """加载粉色结果JSON（兼容剪裁信息）"""
    if not os.path.exists("contour_result.json"):
        messagebox.showerror("错误", "❌ 未找到 contour_result.json，请先检测")
        return None
    try:
        with open("contour_result.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        messagebox.showerror("错误", f"读取粉色JSON失败：{e}")
        return None


def load_white_border_json():
    """加载白色边框独立JSON"""
    if not os.path.exists(WHITE_BORDER_JSON_PATH):
        messagebox.showerror("错误", f"❌ 未找到 {WHITE_BORDER_JSON_PATH}")
        return None
    try:
        with open(WHITE_BORDER_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        messagebox.showerror("错误", f"读取白色JSON失败：{e}")
        return None


def preview_saved_contours():
    """粉色边框预览：沿用原始14等分13列网格，基于剪裁后尺寸"""
    global is_previewing, cap
    if is_previewing:
        return
    data = load_contour_from_json()
    if not data:
        return
    if not init_camera():
        return

    is_previewing = True
    pink_color = (192, 203, 255)
    title = f"预览 - 粉色边框 4行13列（剪裁后 {cropped_width}x{cropped_height}）"

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, display_width, display_height)

    while is_previewing:
        ret, frame = cap.read()
        if not ret:
            break

        # 核心：先做畸变校正+剪裁
        frame = correct_distortion(frame)

        frame_copy = frame.copy()
        contours = data.get("contours", [])

        for c in contours:
            box = np.array(c["bounding_box_coordinates"], np.int32)
            rect = c["bounding_rect"]
            cv2.drawContours(frame_copy, [box], 0, pink_color, 4)
            # 粉色网格（适配剪裁后尺寸）
            frame_copy = draw_pink_grid(frame_copy, rect)

        frame_display = cv2.resize(frame_copy, (display_width, display_height))
        cv2.imshow(title, frame_display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    is_previewing = False
    cap.release()
    cv2.destroyAllWindows()


def preview_white_border():
    """白色边框预览：5列2行，无偏移，基于剪裁后尺寸"""
    global is_previewing_white, cap
    if is_previewing_white:
        return
    data = load_white_border_json()
    if not data:
        return
    if not init_camera():
        return

    is_previewing_white = True
    title = f"预览 - 白色边框 2行5列（剪裁后 {cropped_width}x{cropped_height}）"

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, display_width, display_height)

    while is_previewing_white:
        ret, frame = cap.read()
        if not ret:
            break

        # 核心：先做畸变校正+剪裁
        frame = correct_distortion(frame)

        frame_copy = frame.copy()
        contours = data.get("contours", [])

        for c in contours:
            box = np.array(c["bounding_box_coordinates"], np.int32)
            rect = c["bounding_rect"]
            # 白色粗外框
            cv2.drawContours(frame_copy, [box], 0, WHITE_BORDER_COLOR, WHITE_BORDER_THICKNESS)
            # 白色内部网格：无偏移（适配剪裁后尺寸）
            frame_copy = draw_white_grid(frame_copy, rect)

        frame_display = cv2.resize(frame_copy, (display_width, display_height))
        cv2.imshow(title, frame_display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    is_previewing_white = False
    cap.release()
    cv2.destroyAllWindows()


# 线程启动函数
def start_detect():
    threading.Thread(target=lambda: detect_contours_by_ratio((31.0, 32.0)), daemon=True).start()


def start_pink_preview():
    threading.Thread(target=preview_saved_contours, daemon=True).start()


def start_white_preview():
    threading.Thread(target=preview_white_border, daemon=True).start()


def create_gui():
    root = tk.Tk()
    root.title(f"轮廓检测系统 - 畸变+剪裁响应版（{cropped_width}x{cropped_height}）")
    root.geometry("780x350")
    root.resizable(False, False)

    ttk.Style().configure("TButton", font=("微软雅黑", 12), padding=10)
    ttk.Style().configure("TLabel", font=("微软雅黑", 13))

    # 显示剪裁参数信息
    crop_info = (
        f"📌 粉色边框（检测/预览）：14等分宽度 → 显示13列4行，保留偏移\n"
        f"⚪ 白色边框（预览）：5列2行，无偏移，读取独立 black_border.json\n"
        f"🔧 畸变校正+剪裁：左裁{left_crop}px | 右裁{right_crop}px | 最终尺寸{cropped_width}x{cropped_height}\n"
        f"💡 所有检测/预览均基于剪裁后真实尺寸运行"
    )
    ttk.Label(root, text=crop_info, style="TLabel").pack(pady=15)

    frame_btn = ttk.Frame(root)
    frame_btn.pack(pady=15, padx=30, fill=tk.X)

    ttk.Button(frame_btn, text="开始检测（粉色13列）", command=start_detect) \
        .grid(row=0, column=0, padx=10, sticky=tk.E + tk.W)
    ttk.Button(frame_btn, text="预览粉色边框", command=start_pink_preview) \
        .grid(row=0, column=1, padx=10, sticky=tk.E + tk.W)
    ttk.Button(frame_btn, text="预览白色边框", command=start_white_preview) \
        .grid(row=0, column=2, padx=10, sticky=tk.E + tk.W)

    frame_btn.columnconfigure(0, weight=1)
    frame_btn.columnconfigure(1, weight=1)
    frame_btn.columnconfigure(2, weight=1)

    ttk.Label(root, text="提示：窗口按 q 退出 | 所有操作基于剪裁后真实尺寸",
              font=("微软雅黑", 9), foreground="red").pack(pady=10)

    def on_close():
        global is_previewing, is_detecting, is_previewing_white, cap
        is_previewing = is_detecting = is_previewing_white = False
        if cap:
            cap.release()
        cv2.destroyAllWindows()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    create_gui()