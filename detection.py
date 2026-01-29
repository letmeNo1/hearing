import cv2
import numpy as np
import time

class CameraDetectionDebugger:
    def __init__(self):
        # 针对整体外框检测的优化参数
        self.min_contour_area = 20000          # 只找大轮廓（整个阵列）
        self.area_ratio_min = 15.0             # 适配整个阵列的占比
        self.area_ratio_max = 50.0
        self.blur_kernel = (21, 21)            # 超大模糊核，合并细节
        self.adaptive_block_size = 31          # 更大的块大小
        self.adaptive_C = 10                   # 更强的阈值
        self.camera_id = 1
        self.show_binary = True
        self.is_running = False
        self.last_time = time.time()

    def init_camera(self):
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                print("❌ 无法打开摄像头！")
                return False
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.real_width = int(self.cap.get(3))
        self.real_height = int(self.cap.get(4))
        self.frame_area = self.real_width * self.real_height
        print(f"✅ 摄像头分辨率: {self.real_width}x{self.real_height}")
        return True

    def detect_target(self, frame):
        # 1. 预处理：更强的模糊和二值化
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, self.blur_kernel, 0)
        binary = cv2.adaptiveThreshold(
            blur, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 
            self.adaptive_block_size, 
            self.adaptive_C
        )

        # 2. 关键：超大形态学闭运算，把所有小目标合并成一个大整体
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # 3. 寻找轮廓，只取最大的那个（即整个阵列的外框）
        cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        target_rect = None

        if cnts:
            # 按面积排序，取最大的轮廓
            cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
            largest_cnt = cnts[0]
            largest_area = cv2.contourArea(largest_cnt)

            if largest_area > self.min_contour_area:
                x, y, w, h = cv2.boundingRect(largest_cnt)
                area_ratio = (w * h / self.frame_area) * 100
                print(f"📏 最大轮廓：面积={largest_area:.0f} | 占比={area_ratio:.1f}%")
                if self.area_ratio_min <= area_ratio <= self.area_ratio_max:
                    target_rect = (x, y, w, h)
                    print(f"✅ 找到目标外框：{target_rect}")
                else:
                    print(f"❌ 最大轮廓占比不在范围内 ({self.area_ratio_min}%-{self.area_ratio_max}%)")
            else:
                print(f"❌ 最大轮廓面积不足 ({largest_area} < {self.min_contour_area})")
        else:
            print("❌ 未检测到任何轮廓")

        return target_rect, binary

    def run(self):
        if not self.init_camera():
            return
        
        self.is_running = True
        print("\n=====================================")
        print("🎯 整体外框检测已启动（按Q退出）")
        print("=====================================\n")

        cv2.namedWindow("实时检测画面", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("实时检测画面", 800, 600)
        if self.show_binary:
            cv2.namedWindow("二值化调试画面", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("二值化调试画面", 800, 600)

        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                break

            display_frame = frame.copy()
            target_rect, binary = self.detect_target(frame)

            if target_rect:
                x, y, w, h = target_rect
                cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 4)
                cv2.putText(display_frame, "Target Area", (x, y-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # 计算FPS
            current_time = time.time()
            fps = 1 / (current_time - self.last_time) if (current_time - self.last_time) > 0 else 0
            self.last_time = current_time
            cv2.putText(display_frame, f"FPS: {int(fps)}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

            cv2.imshow("实时检测画面", display_frame)
            if self.show_binary:
                cv2.imshow("二值化调试画面", cv2.resize(binary, (800, 600)))

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                cv2.imwrite("final_debug_frame.png", display_frame)
                cv2.imwrite("final_debug_binary.png", binary)
                print("💾 已保存最终调试图片")

        self.cap.release()
        cv2.destroyAllWindows()
        print("\n👋 检测结束")

if __name__ == "__main__":
    debugger = CameraDetectionDebugger()
    debugger.run()