import cv2
import numpy as np
import json
import os

# 配置常量
CALIBRATION_PARAMS_FILE = "calibration_params.json"
CAM_WIDTH, CAM_HEIGHT = 1920, 1080

# 全局变量（用于存储点击的校准点）
calibration_points = []
click_window_name = "透视变换校准 - 点击顺序：左上→右上→右下→左下"
target_size = (CAM_WIDTH, CAM_HEIGHT)  # 校正后目标尺寸

def on_mouse_click(event, x, y, flags, param):
    """鼠标点击回调函数，收集4个校准点"""
    global calibration_points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(calibration_points) < 4:
            calibration_points.append((x, y))
            # 绘制点击的点（红色圆圈）
            cv2.circle(param, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(param, f"{len(calibration_points)}", (x+10, y), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(click_window_name, param)
            print(f"已选择第{len(calibration_points)}个点：({x}, {y})")
            
            # 选满4个点后自动计算变换矩阵
            if len(calibration_points) == 4:
                calculate_perspective_matrix(param)

def calculate_perspective_matrix(frame):
    """计算透视变换矩阵并保存"""
    global calibration_points
    # 1. 整理源点（用户点击的4个角点）
    src_points = np.array(calibration_points, dtype=np.float32)
    
    # 2. 定义目标点（校正后为规则矩形，铺满目标尺寸）
    dst_points = np.array([
        [0, 0],                      # 左上
        [target_size[0], 0],         # 右上
        [target_size[0], target_size[1]],  # 右下
        [0, target_size[1]]          # 左下
    ], dtype=np.float32)
    
    # 3. 计算透视变换矩阵
    M = cv2.getPerspectiveTransform(src_points, dst_points)
    
    # 4. 验证校正效果（显示校正后的画面）
    corrected_frame = cv2.warpPerspective(frame, M, target_size)
    cv2.imshow("校正效果预览（按任意键保存参数）", corrected_frame)
    cv2.waitKey(0)
    
    # 5. 保存参数到JSON文件
    calibration_data = {
        "perspective_matrix": M.tolist(),
        "cropped_size": target_size,
        "source_points": calibration_points,
        "target_points": dst_points.tolist()
    }
    
    with open(CALIBRATION_PARAMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(calibration_data, f, indent=4)
    
    print(f"\n✅ 透视变换参数已保存到 {CALIBRATION_PARAMS_FILE}")
    print(f"变换矩阵：\n{M}")
    print("\n提示：重启网格监控程序即可使用新的校准参数！")
    
    # 清理窗口
    cv2.destroyAllWindows()

def main():
    """主校准流程"""
    # 初始化摄像头
    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    
    # 读取一帧画面用于校准
    ret, frame = cap.read()
    if not ret:
        print("❌ 无法从摄像头读取画面！")
        cap.release()
        return
    
    cap.release()  # 校准仅需一帧，释放摄像头
    
    # 显示校准窗口并等待点击
    cv2.namedWindow(click_window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(click_window_name, 1280, 720)
    cv2.setMouseCallback(click_window_name, on_mouse_click, frame)
    
    print("📌 校准说明：")
    print("1. 请在画面中依次点击目标区域的4个角点（左上→右上→右下→左下）")
    print("2. 点击后会显示校正效果预览，按任意键保存参数")
    print("3. 若想重新选点，关闭窗口后重新运行脚本\n")
    
    cv2.imshow(click_window_name, frame)
    cv2.waitKey(0)
    
    # 清理
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()