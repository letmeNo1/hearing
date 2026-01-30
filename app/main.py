# main_gui.py
import tkinter as tk
from tkinter import messagebox
import threading
# 业务模块导入
import detection_system
from border_adjuster import adjust_charging_case_border
import calibration_tool
import grid_monitor
# 导入充电日志分析工具（仅导入，不内嵌逻辑）
import charging_log_analysis_tool

# 全局 root 变量
root = None

def run_detection(mode):
    """运行实时监测或预览"""
    global root
    ds = detection_system.DetectionSystem(root)
    threading.Thread(target=ds.worker, args=(mode,), daemon=True).start()

def main_gui():
    """系统主界面入口"""
    global root
    root = tk.Tk()
    root.title("智能视觉标定与检测系统")
    root.geometry("450x700")

    # 标题
    tk.Label(root, text="系统控制面板", font=("微软雅黑", 16, "bold"), pady=20).pack()

    # 按钮样式配置
    btn_style = {"font": ("微软雅黑", 12), "width": 25, "pady": 5}

    # 1. 镜头标定
    tk.Button(root, text="🔧 镜头透视标定", bg="#2196F3", fg="white",
              command=calibration_tool.start_calibration, **btn_style).pack(pady=10)

    # 2. 手动调整黑边
    tk.Button(root, text="📐 手动调整底部区域", bg="#607D8B", fg="white",
              command=adjust_charging_case_border, **btn_style).pack(pady=10)

    # 3. 实时检测
    tk.Button(root, text="🔍 助听器托盘校准", bg="#4CAF50", fg="white",
              command=lambda: run_detection("detect"), **btn_style).pack(pady=10)

    # 4. 预览 HEARING_AID
    tk.Button(root, text="显示助听器托盘预览", bg="#E91E63", fg="white",
              command=lambda: run_detection("hearing_aid"), **btn_style).pack(pady=5)

    # 5. 预览 White
    tk.Button(root, text="显示充电盒托盘预览", bg="#795548", fg="white",
              command=lambda: run_detection("white"), **btn_style).pack(pady=5)

    # 6. 网格监控按钮
    tk.Button(root, text="📹 启动助听器网格监控", bg="#FF9800", fg="white",
              command=lambda: grid_monitor.start_hearing_aid_monitor(root), **btn_style).pack(pady=5)
    tk.Button(root, text="📹 启动充电盒网格监控", bg="#9C27B0", fg="white",
              command=lambda: grid_monitor.start_charging_case_monitor(root), **btn_style).pack(pady=5)

    # 7. 充电日志分析（仅调用工具包的界面函数）
    tk.Button(root, text="📊 充电日志分析", bg="#F44336", fg="white",
              command=lambda: charging_log_analysis_tool.open_log_analyzer_window(root), **btn_style).pack(pady=5)

    # 状态栏
    tk.Label(root, text="提示：按 'S' 保存调整，'Q' 退出预览/监控", fg="gray").pack(side="bottom", pady=20)

    root.mainloop()

if __name__ == "__main__":
    main_gui()